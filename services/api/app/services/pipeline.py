from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, sha256_bytes
from app.models.entities import (
    Chunk,
    ChunkingProfile,
    CleanupProfile,
    DerivedDocumentContent,
    Document,
    DocumentQualityReport,
    DocumentStatus,
    DocumentVersion,
    EmbeddingProfile,
    EmbeddingVector,
    KnowledgeBase,
    Notification,
    PipelineRun,
    PipelineRunDocument,
    PipelineStage,
    ProviderConnection,
)
from app.services.chunking import chunk_text, configuration_hash
from app.services.cleanup import clean_text
from app.services.embeddings import get_embedding_provider
from app.services.eta import StageWork, estimate_completion_seconds
from app.services.extraction import extract_document
from app.services.profiles import ensure_default_profiles
from app.services.quality import analyze_quality
from app.services.storage import get_object_bytes


def process_pipeline_run(db: Session, pipeline_run_id: UUID) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if not run:
        return
    start = time.perf_counter()
    run.started_at = datetime.now(UTC)
    run.current_stage = PipelineStage.VALIDATING
    run.progress_percentage = 2
    db.commit()

    run_docs = list(
        db.scalars(
            select(PipelineRunDocument)
            .where(PipelineRunDocument.pipeline_run_id == run.id)
            .order_by(PipelineRunDocument.created_at)
        )
    )
    run.total_count = len(run_docs)
    db.commit()

    for index, run_doc in enumerate(run_docs, start=1):
        if run.cancelled_at:
            _finish_cancelled(db, run)
            return
        try:
            _process_document(db, run, run_doc)
            run.processed_count = index
            run.progress_percentage = min(95, int(index / max(1, len(run_docs)) * 90) + 5)
            remaining = len(run_docs) - index
            eta, confidence = estimate_completion_seconds(
                0,
                [
                    StageWork("documents", remaining, index / max(1, time.perf_counter() - start), None),
                ],
            )
            run.estimated_completion_seconds = eta
            run.estimated_completion_confidence = confidence
            db.commit()
        except Exception as exc:
            run_doc.status = PipelineStage.FAILED
            run_doc.error = "Document processing failed. See audit logs for operational details."
            run.errors = [*run.errors, {"document_id": str(run_doc.document_id), "message": str(exc)[:500]}]
            db.commit()

    failed = any(doc.status == PipelineStage.FAILED for doc in run_docs)
    if _is_embedding_backfill(run) and not failed and run.embedding_profile_id:
        kb = db.get(KnowledgeBase, run.knowledge_base_id)
        if kb and kb.organization_id == run.organization_id:
            kb.default_embedding_profile_id = run.embedding_profile_id
    warning_count = sum(len(doc.warnings or []) for doc in run_docs)
    run.current_stage = PipelineStage.COMPLETED_WITH_WARNINGS if failed or warning_count else PipelineStage.COMPLETED
    run.progress_percentage = 100
    run.completed_at = datetime.now(UTC)
    run.actual_completion_seconds = int(time.perf_counter() - start)
    db.add(
        Notification(
            organization_id=run.organization_id,
            user_id=None,
            kind="pipeline_completed" if not failed else "pipeline_failed",
            title="Pipeline completed" if not failed else "Pipeline completed with failures",
            body=f"Processed {run.processed_count}/{run.total_count} document(s).",
            severity="success" if not failed else "warning",
            metadata_json={"pipeline_run_id": str(run.id)},
        )
    )
    db.commit()


def _process_document(db: Session, run: PipelineRun, run_doc: PipelineRunDocument) -> None:
    document = db.get(Document, run_doc.document_id)
    if not document or document.organization_id != run.organization_id:
        raise ValueError("Document not found in organization.")
    if _is_embedding_backfill(run):
        _process_embedding_backfill_document(db, run, run_doc, document)
        return
    version = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
    )
    if not version:
        raise ValueError("Document version not found.")

    cleanup_profile = _get_cleanup_profile(db, run.cleanup_profile_id, run.organization_id)
    chunking_profile = _get_chunking_profile(db, run.chunking_profile_id, run.organization_id)
    embedding_profile = _get_embedding_profile(db, run.embedding_profile_id, run.organization_id)

    _stage(db, run, run_doc, PipelineStage.EXTRACTING, document.original_filename, 10)
    data = get_object_bytes(version.s3_object_key)
    checksum = sha256_bytes(data)
    version.checksum = checksum
    version.file_size = len(data)
    document.checksum = checksum
    document.file_size = len(data)
    extracted = extract_document(document.original_filename, data, document.file_type)
    db.add(
        DerivedDocumentContent(
            organization_id=run.organization_id,
            document_id=document.id,
            version_id=version.id,
            kind="extracted",
            text=extracted.text,
            provenance=extracted.provenance,
        )
    )

    _stage(db, run, run_doc, PipelineStage.QUALITY_ANALYSIS, document.original_filename, 25)
    quality = analyze_quality(extracted.text, extracted.warnings)
    db.add(
        DocumentQualityReport(
            organization_id=run.organization_id,
            document_id=document.id,
            version_id=version.id,
            issues=quality.issues,
            severity=quality.severity,
            requires_review=quality.requires_review,
            summary=quality.summary,
        )
    )
    if quality.requires_review and cleanup_profile.pause_on_quality_issues:
        run_doc.status = PipelineStage.AWAITING_REVIEW
        run_doc.warnings = quality.issues
        document.processing_status = DocumentStatus.AWAITING_REVIEW
        db.add(
            Notification(
                organization_id=run.organization_id,
                user_id=document.uploaded_by_user_id,
                kind="pipeline_awaiting_review",
                title="Document awaiting review",
                body=f"{document.name} needs review before indexing.",
                severity="warning",
                metadata_json={"document_id": str(document.id), "pipeline_run_id": str(run.id)},
            )
        )
        db.commit()
        return

    _stage(db, run, run_doc, PipelineStage.CLEANING, document.original_filename, 40)
    cleaned = clean_text(extracted.text, cleanup_profile.strategy, cleanup_profile.config.get("custom_patterns", []))
    db.add_all(
        [
            DerivedDocumentContent(
                organization_id=run.organization_id,
                document_id=document.id,
                version_id=version.id,
                kind="cleaned",
                text=cleaned.cleaned_text,
                provenance=extracted.provenance,
                source_profile_id=cleanup_profile.id,
            ),
            DerivedDocumentContent(
                organization_id=run.organization_id,
                document_id=document.id,
                version_id=version.id,
                kind="redacted",
                text=cleaned.redacted_text,
                provenance=extracted.provenance,
                source_profile_id=cleanup_profile.id,
            ),
        ]
    )
    retrieval_text = {
        "extracted": cleaned.extracted_text,
        "cleaned": cleaned.cleaned_text,
        "redacted": cleaned.redacted_text,
    }.get(cleanup_profile.use_for_retrieval, cleaned.cleaned_text)

    _stage(db, run, run_doc, PipelineStage.CHUNKING, document.original_filename, 55)
    db.execute(delete(EmbeddingVector).where(EmbeddingVector.document_id == document.id))
    db.execute(delete(Chunk).where(Chunk.document_id == document.id))
    cfg_hash = configuration_hash(
        chunking_profile.strategy,
        chunking_profile.chunk_size_tokens,
        chunking_profile.overlap_tokens,
        chunking_profile.config,
    )
    chunks = chunk_text(
        retrieval_text,
        strategy=chunking_profile.strategy,
        chunk_size_tokens=chunking_profile.chunk_size_tokens,
        overlap_tokens=chunking_profile.overlap_tokens,
        provenance=extracted.provenance,
    )
    chunk_models = [
        Chunk(
            organization_id=run.organization_id,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            version_id=version.id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            token_count=chunk.token_count,
            page_start=chunk.provenance.get("page_number"),
            page_end=chunk.provenance.get("page_number"),
            sheet_name=chunk.provenance.get("sheet_name"),
            heading_hierarchy=chunk.heading_hierarchy,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            category_id=document.category_id,
            tags=document.tags,
            confidentiality=document.confidentiality,
            access_policy=document.access_policy,
            chunking_strategy=chunking_profile.strategy,
            chunking_configuration_hash=cfg_hash,
        )
        for chunk in chunks
    ]
    db.add_all(chunk_models)
    db.flush()

    _stage(db, run, run_doc, PipelineStage.EMBEDDING, document.original_filename, 75)
    provider_connection = _get_provider_connection(db, embedding_profile, run.organization_id)
    api_key = (
        decrypt_secret(provider_connection.encrypted_api_key)
        if provider_connection and provider_connection.encrypted_api_key
        else None
    )
    provider = get_embedding_provider(
        embedding_profile.provider.value,
        model_name=embedding_profile.model_name,
        api_key=api_key,
        base_url=provider_connection.base_url if provider_connection else None,
        dimension=embedding_profile.embedding_dimension,
    )
    vectors = asyncio.run(provider.embed_texts([chunk.text for chunk in chunk_models]))
    for vector in vectors:
        if len(vector) != embedding_profile.embedding_dimension:
            raise ValueError(
                f"Embedding provider returned {len(vector)} dimensions; "
                f"profile expects {embedding_profile.embedding_dimension}."
            )
    db.add_all(
        [
            EmbeddingVector(
                organization_id=run.organization_id,
                knowledge_base_id=document.knowledge_base_id,
                document_id=document.id,
                chunk_id=chunk.id,
                embedding_profile_id=embedding_profile.id,
                embedding_model=embedding_profile.model_name,
                embedding_dimension=embedding_profile.embedding_dimension,
                embedding=vector,
            )
            for chunk, vector in zip(chunk_models, vectors, strict=True)
        ]
    )

    _stage(db, run, run_doc, PipelineStage.INDEXING, document.original_filename, 92)
    document.processing_status = (
        DocumentStatus.COMPLETED_WITH_WARNINGS if quality.issues else DocumentStatus.COMPLETED
    )
    run_doc.status = PipelineStage.COMPLETED_WITH_WARNINGS if quality.issues else PipelineStage.COMPLETED
    run_doc.progress_percentage = 100
    run_doc.warnings = [*quality.issues, *cleaned.warnings]
    db.commit()


def _process_embedding_backfill_document(
    db: Session,
    run: PipelineRun,
    run_doc: PipelineRunDocument,
    document: Document,
) -> None:
    embedding_profile = _get_embedding_profile(db, run.embedding_profile_id, run.organization_id)
    chunks = list(
        db.scalars(
            select(Chunk)
            .where(
                Chunk.organization_id == run.organization_id,
                Chunk.document_id == document.id,
            )
            .order_by(Chunk.chunk_index)
        )
    )
    if not chunks:
        raise ValueError("No existing chunks found for embedding backfill. Run full ingestion first.")

    _stage(db, run, run_doc, PipelineStage.EMBEDDING, document.original_filename, 75)
    existing_chunk_ids = {
        chunk_id
        for chunk_id in db.scalars(
            select(EmbeddingVector.chunk_id).where(
                EmbeddingVector.document_id == document.id,
                EmbeddingVector.embedding_profile_id == embedding_profile.id,
            )
        )
    }
    pending_chunks = [chunk for chunk in chunks if chunk.id not in existing_chunk_ids]
    if pending_chunks:
        provider_connection = _get_provider_connection(db, embedding_profile, run.organization_id)
        api_key = (
            decrypt_secret(provider_connection.encrypted_api_key)
            if provider_connection and provider_connection.encrypted_api_key
            else None
        )
        provider = get_embedding_provider(
            embedding_profile.provider.value,
            model_name=embedding_profile.model_name,
            api_key=api_key,
            base_url=provider_connection.base_url if provider_connection else None,
            dimension=embedding_profile.embedding_dimension,
        )
        for start in range(0, len(pending_chunks), embedding_profile.batch_size):
            batch = pending_chunks[start : start + embedding_profile.batch_size]
            vectors = asyncio.run(provider.embed_texts([chunk.text for chunk in batch]))
            for vector in vectors:
                if len(vector) != embedding_profile.embedding_dimension:
                    raise ValueError(
                        f"Embedding provider returned {len(vector)} dimensions; "
                        f"profile expects {embedding_profile.embedding_dimension}."
                    )
            db.add_all(
                [
                    EmbeddingVector(
                        organization_id=run.organization_id,
                        knowledge_base_id=document.knowledge_base_id,
                        document_id=document.id,
                        chunk_id=chunk.id,
                        embedding_profile_id=embedding_profile.id,
                        embedding_model=embedding_profile.model_name,
                        embedding_dimension=embedding_profile.embedding_dimension,
                        embedding=vector,
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ]
            )
            db.flush()

    _stage(db, run, run_doc, PipelineStage.INDEXING, document.original_filename, 92)
    run_doc.status = PipelineStage.COMPLETED
    run_doc.progress_percentage = 100
    run.worker_logs = [
        *run.worker_logs[-100:],
        {
            "stage": PipelineStage.INDEXING.value,
            "item": document.original_filename,
            "message": (
                f"Backfilled {len(pending_chunks)} missing embedding(s); "
                f"preserved {len(existing_chunk_ids)} existing embedding(s)."
            ),
            "at": datetime.now(UTC).isoformat(),
        },
    ]
    db.commit()


def _stage(
    db: Session,
    run: PipelineRun,
    run_doc: PipelineRunDocument,
    stage: PipelineStage,
    item: str,
    progress: int,
) -> None:
    run.current_stage = stage
    run.current_item = item
    run.progress_percentage = max(run.progress_percentage, progress)
    run.worker_logs = [
        *run.worker_logs[-100:],
        {"stage": stage.value, "item": item, "message": "Stage started", "at": datetime.now(UTC).isoformat()},
    ]
    run_doc.status = stage
    run_doc.progress_percentage = progress
    db.commit()


def _finish_cancelled(db: Session, run: PipelineRun) -> None:
    run.current_stage = PipelineStage.CANCELLED
    run.completed_at = datetime.now(UTC)
    db.commit()


def _get_cleanup_profile(db: Session, profile_id: UUID | None, org_id: UUID) -> CleanupProfile:
    query = select(CleanupProfile).where(CleanupProfile.organization_id.in_([org_id, None]))
    if profile_id:
        query = query.where(CleanupProfile.id == profile_id)
    else:
        query = query.order_by(CleanupProfile.organization_id.desc().nullslast(), CleanupProfile.created_at)
    profile = db.scalar(query)
    if not profile:
        raise ValueError("Cleanup profile not found.")
    return profile


def _get_chunking_profile(db: Session, profile_id: UUID | None, org_id: UUID) -> ChunkingProfile:
    query = select(ChunkingProfile).where(ChunkingProfile.organization_id.in_([org_id, None]))
    if profile_id:
        query = query.where(ChunkingProfile.id == profile_id)
    else:
        query = query.order_by(ChunkingProfile.organization_id.desc().nullslast(), ChunkingProfile.created_at)
    profile = db.scalar(query)
    if not profile:
        raise ValueError("Chunking profile not found.")
    return profile


def _get_embedding_profile(db: Session, profile_id: UUID | None, org_id: UUID) -> EmbeddingProfile:
    ensure_default_profiles(db, org_id)
    db.flush()
    query = select(EmbeddingProfile).where(EmbeddingProfile.organization_id.in_([org_id, None]))
    if profile_id:
        query = query.where(EmbeddingProfile.id == profile_id)
    else:
        query = query.where(EmbeddingProfile.is_active.is_(True)).order_by(EmbeddingProfile.created_at)
    profile = db.scalar(query)
    if not profile:
        raise ValueError("Embedding profile not found.")
    return profile


def _is_embedding_backfill(run: PipelineRun) -> bool:
    config = run.retrieval_index_config or {}
    return config.get("migration_mode") == "embedding_backfill" or config.get("embedding_backfill") is True


def _get_provider_connection(
    db: Session,
    embedding_profile: EmbeddingProfile,
    org_id: UUID,
) -> ProviderConnection | None:
    if embedding_profile.provider.value == "Local":
        return None
    if not embedding_profile.provider_connection_id:
        raise ValueError("Embedding profile requires a provider connection.")
    connection = db.get(ProviderConnection, embedding_profile.provider_connection_id)
    if (
        not connection
        or connection.organization_id != org_id
        or connection.deleted_at is not None
        or not connection.is_enabled
    ):
        raise ValueError("Embedding provider connection is not available.")
    if connection.provider != embedding_profile.provider:
        raise ValueError("Embedding profile provider does not match its provider connection.")
    return connection
