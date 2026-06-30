from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import sha256_bytes
from app.models.entities import (
    ConfidentialityLevel,
    Document,
    DocumentStatus,
    DocumentVersion,
    KnowledgeBase,
    PipelineRun,
    PipelineRunDocument,
    PipelineStage,
)
from app.services.storage import build_object_key, put_object_bytes, validate_upload

RETRIEVAL_DEFAULT_KEYS = {
    "retrieval_algorithm",
    "max_chunks",
    "vector_candidate_count",
    "keyword_candidate_count",
    "rerank_candidates",
    "rrf_constant",
    "similarity_threshold",
}


def create_uploaded_document_from_bytes(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_base_id: UUID,
    filename: str,
    data: bytes,
    content_type: str | None,
    uploaded_by_user_id: UUID | None = None,
    category_id: UUID | None = None,
    tags: list[str] | None = None,
    business_unit: str | None = None,
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.INTERNAL,
    source_url: str | None = None,
    custom_metadata: dict | None = None,
) -> Document:
    file_type = validate_upload(filename, content_type, len(data))
    document = Document(
        organization_id=organization_id,
        knowledge_base_id=knowledge_base_id,
        category_id=category_id,
        name=filename,
        original_filename=filename,
        file_type=file_type,
        file_size=len(data),
        s3_object_key="pending",
        tags=tags or [],
        business_unit=business_unit,
        confidentiality=confidentiality,
        source_url=source_url,
        created_by_user_id=uploaded_by_user_id,
        uploaded_by_user_id=uploaded_by_user_id,
        custom_metadata=custom_metadata or {},
        processing_status=DocumentStatus.UPLOADED,
    )
    db.add(document)
    db.flush()
    version = DocumentVersion(
        organization_id=organization_id,
        document_id=document.id,
        version_number=1,
        s3_object_key="pending",
        filename=filename,
        checksum=sha256_bytes(data),
        file_size=len(data),
    )
    db.add(version)
    db.flush()
    object_key = build_object_key(
        str(organization_id), str(knowledge_base_id), str(document.id), str(version.id), filename
    )
    put_object_bytes(object_key, data, content_type)
    document.s3_object_key = object_key
    document.checksum = version.checksum
    version.s3_object_key = object_key
    return document


def queue_pipeline_for_documents(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_base_id: UUID,
    document_ids: list[UUID],
    cleanup_profile_id: UUID | None = None,
    chunking_profile_id: UUID | None = None,
    embedding_profile_id: UUID | None = None,
    retrieval_index_config: dict | None = None,
) -> PipelineRun:
    kb = db.get(KnowledgeBase, knowledge_base_id)
    if kb and kb.organization_id == organization_id:
        apply_retrieval_defaults(kb, retrieval_index_config or {})
        if embedding_profile_id:
            kb.default_embedding_profile_id = embedding_profile_id
    run = PipelineRun(
        organization_id=organization_id,
        knowledge_base_id=knowledge_base_id,
        cleanup_profile_id=cleanup_profile_id,
        chunking_profile_id=chunking_profile_id,
        embedding_profile_id=embedding_profile_id,
        retrieval_index_config=retrieval_index_config or {"max_chunks": 8, "rrf_constant": 60},
        current_stage=PipelineStage.QUEUED,
        total_count=len(document_ids),
        estimated_completion_seconds=max(30, len(document_ids) * 15),
        estimated_completion_confidence="Low",
    )
    db.add(run)
    db.flush()
    for document_id in document_ids:
        document = db.get(Document, document_id)
        if document:
            document.processing_status = DocumentStatus.QUEUED
        db.add(
            PipelineRunDocument(
                organization_id=organization_id,
                pipeline_run_id=run.id,
                document_id=document_id,
                status=PipelineStage.QUEUED,
            )
    )
    db.commit()
    from app.workers.tasks import process_pipeline_run_task

    process_pipeline_run_task.delay(str(run.id))
    db.refresh(run)
    return run


def apply_retrieval_defaults(kb: KnowledgeBase, retrieval_index_config: dict) -> None:
    defaults = {
        key: retrieval_index_config[key]
        for key in RETRIEVAL_DEFAULT_KEYS
        if key in retrieval_index_config and retrieval_index_config[key] is not None
    }
    if defaults:
        kb.default_retrieval_config = {**(kb.default_retrieval_config or {}), **defaults}
