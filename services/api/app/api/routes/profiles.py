from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_organization
from app.db.session import get_db
from app.models.entities import ChunkingProfile, CleanupProfile, EmbeddingProfile
from app.services.profiles import ensure_default_profiles

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
def list_profiles(ctx: AuthContext = Depends(require_organization), db: Session = Depends(get_db)) -> dict:
    ensure_default_profiles(db, ctx.organization_id)
    db.commit()
    return {
        "cleanup_profiles": [
            {
                "id": str(profile.id),
                "name": profile.name,
                "strategy": profile.strategy,
                "use_for_retrieval": profile.use_for_retrieval,
                "pause_on_quality_issues": profile.pause_on_quality_issues,
                "config": profile.config,
            }
            for profile in db.scalars(
                select(CleanupProfile).where(CleanupProfile.organization_id == ctx.organization_id)
            )
        ],
        "chunking_profiles": [
            {
                "id": str(profile.id),
                "name": profile.name,
                "strategy": profile.strategy,
                "chunk_size_tokens": profile.chunk_size_tokens,
                "overlap_tokens": profile.overlap_tokens,
                "config": profile.config,
            }
            for profile in db.scalars(
                select(ChunkingProfile).where(ChunkingProfile.organization_id == ctx.organization_id)
            )
        ],
        "embedding_profiles": [
            {
                "id": str(profile.id),
                "name": profile.name,
                "provider": profile.provider.value,
                "model_name": profile.model_name,
                "embedding_dimension": profile.embedding_dimension,
                "is_active": profile.is_active,
                "config": profile.config,
            }
            for profile in db.scalars(
                select(EmbeddingProfile).where(EmbeddingProfile.organization_id == ctx.organization_id)
            )
        ],
    }
