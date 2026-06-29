from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, request_meta
from app.core.config import settings
from app.core.security import sha256_bytes
from app.db.session import get_db
from app.models.entities import Document, DocumentStatus, DocumentVersion, KnowledgeBase
from app.schemas.api import UploadCompleteIn, UploadPresignIn, UploadPresignOut
from app.services.audit import write_audit_log
from app.services.storage import (
    build_object_key,
    create_multipart_presigned_urls,
    create_presigned_put,
    get_object_bytes,
    head_object,
    internal_s3_client,
    validate_upload,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])


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
