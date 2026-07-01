from __future__ import annotations

import json
import mimetypes
import tarfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, request_meta
from app.core.config import settings
from app.core.security import sha256_bytes
from app.db.session import get_db
from app.models.entities import (
    Category,
    ConfidentialityLevel,
    Document,
    DocumentStatus,
    DocumentVersion,
    KnowledgeBase,
)
from app.schemas.api import DocumentOut, UploadCompleteIn, UploadPresignIn, UploadPresignOut
from app.services.audit import write_audit_log
from app.services.document_ingestion import create_uploaded_document_from_bytes
from app.services.storage import (
    SUPPORTED_EXTENSIONS,
    build_object_key,
    create_multipart_presigned_urls,
    create_presigned_put,
    get_object_bytes,
    head_object,
    internal_s3_client,
    put_object_bytes,
    validate_upload,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])

MAX_ARCHIVE_FILES = 500


@dataclass(frozen=True)
class ArchiveMember:
    path: PurePosixPath
    data: bytes
    content_type: str | None


@router.post("", response_model=DocumentOut)
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    knowledge_base_id: UUID = Form(...),
    category_id: UUID | None = Form(default=None),
    tags: str = Form(default="[]"),
    business_unit: str | None = Form(default=None),
    confidentiality: ConfidentialityLevel = Form(default=ConfidentialityLevel.INTERNAL),
    source_url: str | None = Form(default=None),
    custom_metadata: str = Form(default="{}"),
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> Document:
    kb = db.get(KnowledgeBase, knowledge_base_id)
    if not kb or kb.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")

    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    data = _read_upload_bytes(file)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Upload cannot be empty.")

    parsed_tags = _parse_tags_form(tags)
    parsed_metadata = _parse_metadata_form(custom_metadata)
    file_type = validate_upload(filename, content_type, len(data))
    checksum = sha256_bytes(data)

    document = Document(
        organization_id=ctx.organization_id,
        knowledge_base_id=knowledge_base_id,
        category_id=category_id,
        name=filename,
        original_filename=filename,
        file_type=file_type,
        file_size=len(data),
        s3_object_key="pending",
        tags=parsed_tags,
        business_unit=business_unit or None,
        confidentiality=confidentiality,
        source_url=source_url or None,
        created_by_user_id=ctx.user.id,
        uploaded_by_user_id=ctx.user.id,
        custom_metadata=parsed_metadata,
        processing_status=DocumentStatus.UPLOADED,
        checksum=checksum,
    )
    db.add(document)
    db.flush()
    version = DocumentVersion(
        organization_id=ctx.organization_id,
        document_id=document.id,
        version_number=1,
        s3_object_key="pending",
        filename=filename,
        file_size=len(data),
        checksum=checksum,
    )
    db.add(version)
    db.flush()

    object_key = build_object_key(
        str(ctx.organization_id), str(knowledge_base_id), str(document.id), str(version.id), filename
    )
    put_object_bytes(object_key, data, content_type)
    document.s3_object_key = object_key
    version.s3_object_key = object_key

    duplicate = db.scalar(
        select(Document).where(
            Document.organization_id == ctx.organization_id,
            Document.checksum == checksum,
            Document.id != document.id,
            Document.deleted_at.is_(None),
        )
    )
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="upload.completed",
        resource_type="document",
        resource_id=str(document.id),
        metadata={
            "checksum": checksum,
            "duplicate_document_id": str(duplicate.id) if duplicate else None,
            "filename": filename,
            "size_bytes": len(data),
            "transport": "api",
        },
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(document)
    return document


@router.post("/archive", response_model=list[DocumentOut])
def upload_archive(
    request: Request,
    file: UploadFile = File(...),
    knowledge_base_id: UUID = Form(...),
    category_id: UUID | None = Form(default=None),
    tags: str = Form(default="[]"),
    business_unit: str | None = Form(default=None),
    confidentiality: ConfidentialityLevel = Form(default=ConfidentialityLevel.INTERNAL),
    custom_metadata: str = Form(default="{}"),
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> list[Document]:
    kb = db.get(KnowledgeBase, knowledge_base_id)
    if not kb or kb.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    base_category = _get_category(db, ctx.organization_id, knowledge_base_id, category_id) if category_id else None
    archive_name = file.filename or "archive"
    data = _read_upload_bytes(file)
    members = _read_archive_members(archive_name, data)
    if not members:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Archive does not contain supported documents.")

    parsed_tags = _parse_tags_form(tags)
    parsed_metadata = _parse_metadata_form(custom_metadata)
    documents: list[Document] = []
    for member in members:
        member_category_id = _ensure_archive_category(
            db,
            organization_id=ctx.organization_id,
            knowledge_base_id=knowledge_base_id,
            base_category=base_category,
            folder_parts=list(member.path.parent.parts),
        )
        document = create_uploaded_document_from_bytes(
            db,
            organization_id=ctx.organization_id,
            knowledge_base_id=knowledge_base_id,
            category_id=member_category_id,
            filename=member.path.name,
            data=member.data,
            content_type=member.content_type,
            uploaded_by_user_id=ctx.user.id,
            tags=parsed_tags,
            business_unit=business_unit or None,
            confidentiality=confidentiality,
            source_url=f"archive:{archive_name}:{member.path.as_posix()}",
            custom_metadata={
                **parsed_metadata,
                "archive_name": archive_name,
                "archive_path": member.path.as_posix(),
            },
        )
        documents.append(document)

    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="upload.archive_completed",
        resource_type="document",
        metadata={
            "filename": archive_name,
            "document_count": len(documents),
            "transport": "archive",
        },
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    for document in documents:
        db.refresh(document)
    return documents


@router.post("/presign", response_model=UploadPresignOut)
def presign_upload(
    payload: UploadPresignIn,
    request: Request,
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> UploadPresignOut:
    kb = db.get(KnowledgeBase, payload.knowledge_base_id)
    if not kb or kb.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    file_type = validate_upload(payload.filename, payload.content_type, payload.size_bytes)
    document = Document(
        organization_id=ctx.organization_id,
        knowledge_base_id=payload.knowledge_base_id,
        category_id=payload.category_id,
        name=payload.filename,
        original_filename=payload.filename,
        file_type=file_type,
        file_size=payload.size_bytes,
        s3_object_key="pending",
        tags=payload.tags,
        business_unit=payload.business_unit,
        confidentiality=payload.confidentiality,
        source_url=payload.source_url,
        created_by_user_id=ctx.user.id,
        uploaded_by_user_id=ctx.user.id,
        custom_metadata=payload.custom_metadata,
        processing_status=DocumentStatus.DRAFT,
    )
    db.add(document)
    db.flush()
    version = DocumentVersion(
        organization_id=ctx.organization_id,
        document_id=document.id,
        version_number=1,
        s3_object_key="pending",
        filename=payload.filename,
        file_size=payload.size_bytes,
    )
    db.add(version)
    db.flush()
    object_key = build_object_key(
        str(ctx.organization_id), str(payload.knowledge_base_id), str(document.id), str(version.id), payload.filename
    )
    document.s3_object_key = object_key
    version.s3_object_key = object_key
    target = (
        create_multipart_presigned_urls(object_key, payload.content_type, payload.size_bytes)
        if payload.size_bytes >= settings.multipart_threshold_bytes
        else create_presigned_put(object_key, payload.content_type)
    )
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="upload.presigned",
        resource_type="document",
        resource_id=str(document.id),
        metadata={"filename": payload.filename, "size_bytes": payload.size_bytes},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    return UploadPresignOut(
        document_id=document.id,
        version_id=version.id,
        object_key=object_key,
        upload_url=target.upload_url,
        headers=target.headers,
        multipart=target.multipart,
        upload_id=target.upload_id,
        part_urls=target.part_urls,
    )


@router.post("/complete")
def complete_upload(
    payload: UploadCompleteIn,
    request: Request,
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> dict:
    document = db.get(Document, payload.document_id)
    if not document or document.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document.id))
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    if payload.upload_id and payload.parts:
        internal_s3_client().complete_multipart_upload(
            Bucket=settings.s3_bucket,
            Key=version.s3_object_key,
            UploadId=payload.upload_id,
            MultipartUpload={"Parts": payload.parts},
        )
    head = head_object(version.s3_object_key)
    data = get_object_bytes(version.s3_object_key)
    checksum = sha256_bytes(data)
    duplicate = db.scalar(
        select(Document).where(
            Document.organization_id == ctx.organization_id,
            Document.checksum == checksum,
            Document.id != document.id,
            Document.deleted_at.is_(None),
        )
    )
    document.file_size = int(head.get("ContentLength") or len(data))
    document.checksum = checksum
    document.processing_status = DocumentStatus.UPLOADED
    version.file_size = document.file_size
    version.checksum = checksum
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="upload.completed",
        resource_type="document",
        resource_id=str(document.id),
        metadata={"checksum": checksum, "duplicate_document_id": str(duplicate.id) if duplicate else None},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    return {
        "message": "Upload completed.",
        "document_id": str(document.id),
        "checksum": checksum,
        "duplicate_document_id": str(duplicate.id) if duplicate else None,
    }


def _read_upload_bytes(file: UploadFile) -> bytes:
    data = bytearray()
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload is too large.")
    return bytes(data)


def _read_archive_members(filename: str, data: bytes) -> list[ArchiveMember]:
    suffixes = [suffix.lower() for suffix in PurePosixPath(filename).suffixes]
    if suffixes and suffixes[-1] == ".zip":
        return _read_zip_members(data)
    if suffixes and (suffixes[-1] in {".tar", ".tgz"} or suffixes[-2:] == [".tar", ".gz"]):
        return _read_tar_members(data)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Upload a .zip, .tar, .tar.gz, or .tgz archive.")


def _read_zip_members(data: bytes) -> list[ArchiveMember]:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            members = []
            total_size = 0
            for info in archive.infolist():
                if info.is_dir() or _is_archive_system_path(info.filename):
                    continue
                path = _safe_archive_path(info.filename)
                if PurePosixPath(path.name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                total_size += info.file_size
                _enforce_archive_limits(len(members) + 1, total_size)
                members.append(ArchiveMember(path=path, data=archive.read(info), content_type=_guess_content_type(path.name)))
            return members
    except zipfile.BadZipFile as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Archive is not a valid ZIP file.") from exc


def _read_tar_members(data: bytes) -> list[ArchiveMember]:
    try:
        with tarfile.open(fileobj=BytesIO(data), mode="r:*") as archive:
            members = []
            total_size = 0
            for info in archive.getmembers():
                if not info.isfile() or _is_archive_system_path(info.name):
                    continue
                path = _safe_archive_path(info.name)
                if PurePosixPath(path.name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                total_size += info.size
                _enforce_archive_limits(len(members) + 1, total_size)
                extracted = archive.extractfile(info)
                if not extracted:
                    continue
                members.append(ArchiveMember(path=path, data=extracted.read(), content_type=_guess_content_type(path.name)))
            return members
    except tarfile.TarError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Archive is not a valid TAR file.") from exc


def _safe_archive_path(raw_path: str) -> PurePosixPath:
    normalized = raw_path.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if not path.name or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Archive contains an unsafe path: {raw_path}")
    return path


def _is_archive_system_path(raw_path: str) -> bool:
    path = raw_path.replace("\\", "/").strip("/")
    return path.startswith("__MACOSX/") or PurePosixPath(path).name in {".DS_Store", "Thumbs.db"}


def _enforce_archive_limits(file_count: int, total_size: int) -> None:
    if file_count > MAX_ARCHIVE_FILES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Archive contains more than {MAX_ARCHIVE_FILES} files.")
    if total_size > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Expanded archive contents are too large.")


def _guess_content_type(filename: str) -> str | None:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed


def _get_category(
    db: Session,
    organization_id: UUID,
    knowledge_base_id: UUID,
    category_id: UUID | None,
) -> Category:
    category = db.get(Category, category_id)
    if (
        not category
        or category.organization_id != organization_id
        or category.knowledge_base_id != knowledge_base_id
        or category.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found.")
    return category


def _ensure_archive_category(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_base_id: UUID,
    base_category: Category | None,
    folder_parts: list[str],
) -> UUID | None:
    parent = base_category
    current_path = parent.path if parent else ""
    for part in folder_parts:
        current_path = f"{current_path}/{part}" if current_path else part
        category = db.scalar(
            select(Category).where(
                Category.organization_id == organization_id,
                Category.knowledge_base_id == knowledge_base_id,
                Category.path == current_path,
                Category.deleted_at.is_(None),
            )
        )
        if not category:
            category = Category(
                organization_id=organization_id,
                knowledge_base_id=knowledge_base_id,
                parent_id=parent.id if parent else None,
                name=part,
                path=current_path,
                access_policy={},
            )
            db.add(category)
            db.flush()
        parent = category
    return parent.id if parent else None


def _parse_tags_form(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tags must be a list of strings.")
    return [item.strip() for item in parsed if item.strip()]


def _parse_metadata_form(value: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Custom metadata must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Custom metadata must be an object.")
    return parsed
