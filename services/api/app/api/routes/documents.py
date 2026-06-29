from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, require_organization
from app.db.session import get_db
from app.models.entities import (
    DerivedDocumentContent,
    Document,
    DocumentQualityReport,
    DocumentStatus,
)
from app.schemas.api import DocumentOut, DocumentPatchIn, ReviewActionIn

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
    else:
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


def _get_document(db: Session, organization_id: UUID, document_id: UUID) -> Document:
    document = db.get(Document, document_id)
    if not document or document.organization_id != organization_id or document.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


def _latest_version_id(db: Session, document_id: UUID) -> UUID:
    from app.models.entities import DocumentVersion

    version_id = db.scalar(
        select(DocumentVersion.id)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )
    if not version_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    return version_id
