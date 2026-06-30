from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    ChunkingProfile,
    CleanupProfile,
    EmbeddingProfile,
    ProviderKind,
)


def ensure_default_profiles(db: Session, organization_id: UUID | None = None) -> None:
    existing_cleanup = db.scalar(
        select(CleanupProfile).where(CleanupProfile.organization_id == organization_id)
    )
    if not existing_cleanup:
        db.add_all(
            [
                CleanupProfile(
                    organization_id=organization_id,
                    name="Preserve Raw Text",
                    strategy="preserve_raw",
                    use_for_retrieval="extracted",
                    pause_on_quality_issues=True,
                ),
                CleanupProfile(
                    organization_id=organization_id,
                    name="Standard Enterprise Cleanup",
                    strategy="standard",
                    use_for_retrieval="cleaned",
                    pause_on_quality_issues=True,
                ),
                CleanupProfile(
                    organization_id=organization_id,
                    name="Aggressive Cleanup",
                    strategy="aggressive",
                    use_for_retrieval="cleaned",
                    pause_on_quality_issues=True,
                ),
                CleanupProfile(
                    organization_id=organization_id,
                    name="PII and Sensitive Data Redaction",
                    strategy="redaction",
                    use_for_retrieval="redacted",
                    pause_on_quality_issues=True,
                ),
            ]
        )

    existing_chunking = db.scalar(
        select(ChunkingProfile).where(ChunkingProfile.organization_id == organization_id)
    )
    if not existing_chunking:
        db.add_all(
            [
                ChunkingProfile(
                    organization_id=organization_id,
                    name="Recursive Token Chunking",
                    strategy="recursive",
                    chunk_size_tokens=850,
                    overlap_tokens=120,
                ),
                ChunkingProfile(
                    organization_id=organization_id,
                    name="Document-Aware Chunking",
                    strategy="document_aware",
                    chunk_size_tokens=900,
                    overlap_tokens=120,
                ),
                ChunkingProfile(
                    organization_id=organization_id,
                    name="Parent-Child Chunking",
                    strategy="parent_child",
                    chunk_size_tokens=700,
                    overlap_tokens=100,
                ),
                ChunkingProfile(
                    organization_id=organization_id,
                    name="Semantic Chunking",
                    strategy="semantic",
                    chunk_size_tokens=900,
                    overlap_tokens=80,
                ),
            ]
        )

    existing_embedding = db.scalar(
        select(EmbeddingProfile).where(EmbeddingProfile.organization_id == organization_id)
    )
    if not existing_embedding:
        db.add(
            EmbeddingProfile(
                organization_id=organization_id,
                name="Local deterministic embedding",
                provider=ProviderKind.LOCAL,
                model_name="deterministic-local-384",
                embedding_dimension=384,
                batch_size=64,
                normalization="l2",
                is_active=True,
            )
        )


def default_pipeline_profile_ids(db: Session, organization_id: UUID) -> dict[str, UUID | None]:
    ensure_default_profiles(db, organization_id)
    db.flush()
    cleanup = db.scalar(
        select(CleanupProfile)
        .where(CleanupProfile.organization_id == organization_id, CleanupProfile.deleted_at.is_(None))
        .order_by(
            (CleanupProfile.name == "Standard Enterprise Cleanup").desc(),
            CleanupProfile.created_at,
        )
    )
    chunking = db.scalar(
        select(ChunkingProfile)
        .where(ChunkingProfile.organization_id == organization_id, ChunkingProfile.deleted_at.is_(None))
        .order_by(
            (ChunkingProfile.name == "Document-Aware Chunking").desc(),
            (ChunkingProfile.name == "Recursive Token Chunking").desc(),
            ChunkingProfile.created_at,
        )
    )
    embedding = db.scalar(
        select(EmbeddingProfile)
        .where(EmbeddingProfile.organization_id == organization_id, EmbeddingProfile.deleted_at.is_(None))
        .order_by(EmbeddingProfile.is_active.desc(), EmbeddingProfile.created_at)
    )
    return {
        "cleanup_profile_id": cleanup.id if cleanup else None,
        "chunking_profile_id": chunking.id if chunking else None,
        "embedding_profile_id": embedding.id if embedding else None,
    }
