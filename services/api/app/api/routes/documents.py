from __future__ import annotations

import mimetypes
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, request_meta, require_organization
from app.core.config import settings
from app.core.security import sha256_bytes
from app.db.session import get_db
from app.models.entities import (
    DerivedDocumentContent,
    Document,
    DocumentQualityReport,
    DocumentStatus,
    DocumentVersion,
)
from app.schemas.api import DocumentOut, DocumentPatchIn, ReviewActionIn
from app.services.audit import write_audit_log
from app.services.storage import (
    build_object_key,
    get_object_bytes,
    put_object_bytes,
    validate_upload,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(
    knowledge_base_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[Document]:
    query = select(Document).where(Document.organization_id == ctx.organization_id, Document.deleted_at.is_(None))
    if knowledge_base_id:
        query = query.where(Document.knowledge_base_id == knowledge_base_id)
    if search:
        query = query.where(Document.name.ilike(f"%{search}%"))
    if status_filter:
        query = query.where(Document.processing_status == status_filter)
    return list(db.scalars(query.order_by(Document.updated_at.desc())))


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> Document:
    return _get_document(db, ctx.organization_id, document_id)


@router.patch("/{document_id}", response_model=DocumentOut)
def patch_document(
    document_id: UUID,
    payload: DocumentPatchIn,
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> Document:
    document = _get_document(db, ctx.organization_id, document_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(document, key, value)
    db.commit()
    db.refresh(document)
    return document


@router.delete("/{document_id}")
def delete_document(
    document_id: UUID,
    hard: bool = False,
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> dict:
    document = _get_document(db, ctx.organization_id, document_id)
    if hard:
        document.processing_status = DocumentStatus.DELETED
        db.delete(document)
    else:
        document.deleted_at = datetime.now(UTC)
        document.processing_status = DocumentStatus.DELETED
    db.commit()
    return {"message": "Document deleted."}


@router.post("/{document_id}/replace", response_model=DocumentOut)
def replace_document_file(
    document_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(capability("upload_documents")),
    db: Session = Depends(get_db),
) -> Document:
    document = _get_document(db, ctx.organization_id, document_id)
    filename = file.filename or document.original_filename
    content_type = file.content_type or "application/octet-stream"
    data = _read_upload_bytes(file)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Upload cannot be empty.")

    file_type = validate_upload(filename, content_type, len(data))
    checksum = sha256_bytes(data)
    latest_version = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
    )
    next_version_number = (latest_version.version_number if latest_version else document.version_number) + 1
    version = DocumentVersion(
        organization_id=ctx.organization_id,
        document_id=document.id,
        version_number=next_version_number,
        s3_object_key="pending",
        filename=filename,
        file_size=len(data),
        checksum=checksum,
    )
    db.add(version)
    db.flush()

    object_key = build_object_key(
        str(ctx.organization_id), str(document.knowledge_base_id), str(document.id), str(version.id), filename
    )
    put_object_bytes(object_key, data, content_type)
    version.s3_object_key = object_key
    previous_filename = document.original_filename
    document.original_filename = filename
    document.file_type = file_type
    document.file_size = len(data)
    document.s3_object_key = object_key
    document.version_number = next_version_number
    document.checksum = checksum
    document.processing_status = DocumentStatus.UPLOADED
    document.uploaded_by_user_id = ctx.user.id

    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="document.replaced",
        resource_type="document",
        resource_id=str(document.id),
        metadata={
            "previous_filename": previous_filename,
            "filename": filename,
            "version_number": next_version_number,
            "checksum": checksum,
            "size_bytes": len(data),
        },
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(document)
    return document


@router.get("/{document_id}/quality-report")
def get_quality_report(
    document_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> dict:
    document = _get_document(db, ctx.organization_id, document_id)
    report = db.scalar(
        select(DocumentQualityReport)
        .where(DocumentQualityReport.document_id == document.id)
        .order_by(DocumentQualityReport.created_at.desc())
    )
    if not report:
        return {"issues": [], "severity": "pending", "requires_review": False, "summary": "No report yet."}
    return {
        "id": str(report.id),
        "issues": report.issues,
        "severity": report.severity,
        "requires_review": report.requires_review,
        "summary": report.summary,
        "created_at": report.created_at,
    }


@router.post("/{document_id}/review-action")
def review_action(
    document_id: UUID,
    payload: ReviewActionIn,
    ctx: AuthContext = Depends(capability("run_ingestion")),
    db: Session = Depends(get_db),
) -> dict:
    document = _get_document(db, ctx.organization_id, document_id)
    if payload.action == "exclude_document":
        document.processing_status = DocumentStatus.CANCELLED
    elif payload.action == "manual_edit":
        if not payload.edited_text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Manual edit requires edited_text.")
        db.add(
            DerivedDocumentContent(
                organization_id=ctx.organization_id,
                document_id=document.id,
                version_id=_latest_version_id(db, document.id),
                kind="manual_edit",
                text=payload.edited_text,
                provenance=[],
                created_by=str(ctx.user.id),
            )
        )
        document.processing_status = DocumentStatus.UPLOADED
        _record_quality_review_override(document, payload.action, ctx.user.id)
    else:
        _record_quality_review_override(document, payload.action, ctx.user.id)
        document.processing_status = DocumentStatus.UPLOADED
    db.commit()
    return {"message": "Review action recorded.", "document_status": document.processing_status.value}


@router.get("/{document_id}/preview")
def preview_document(
    document_id: UUID,
    kind: str = "cleaned",
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> dict:
    document = _get_document(db, ctx.organization_id, document_id)
    content = db.scalar(
        select(DerivedDocumentContent)
        .where(DerivedDocumentContent.document_id == document.id, DerivedDocumentContent.kind == kind)
        .order_by(DerivedDocumentContent.created_at.desc())
    )
    if not content:
        content = db.scalar(
            select(DerivedDocumentContent)
            .where(DerivedDocumentContent.document_id == document.id)
            .order_by(DerivedDocumentContent.created_at.desc())
        )
    return {"kind": content.kind if content else None, "text": content.text[:20000] if content else ""}


@router.get("/{document_id}/download")
def download_document(
    document_id: UUID,
    disposition: str = Query(default="attachment", pattern="^(attachment|inline)$"),
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> Response:
    document = _get_document(db, ctx.organization_id, document_id)
    data = get_object_bytes(document.s3_object_key)
    content_type = mimetypes.guess_type(document.original_filename)[0] or "application/octet-stream"
    filename = quote(document.original_filename)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}"},
    )


def _get_document(db: Session, organization_id: UUID, document_id: UUID) -> Document:
    document = db.get(Document, document_id)
    if not document or document.organization_id != organization_id or document.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


def _latest_version_id(db: Session, document_id: UUID) -> UUID:
    version_id = db.scalar(
        select(DocumentVersion.id)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )
    if not version_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    return version_id


def _record_quality_review_override(document: Document, action: str, user_id: UUID) -> None:
    document.custom_metadata = {
        **(document.custom_metadata or {}),
        "quality_review_override": {
            "action": action,
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_by_user_id": str(user_id),
            "version_number": document.version_number,
            "checksum": document.checksum,
        },
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
