from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, require_organization
from app.db.session import get_db
from app.models.entities import (
    ChunkingProfile,
    CleanupProfile,
    EmbeddingProfile,
    ModelProfile,
    ProfileKind,
    ProviderConnection,
    ProviderKind,
)
from app.schemas.api import EmbeddingProfileCreateIn, ModelProfileCreateIn
from app.services.profiles import ensure_default_profiles
from app.services.providers import embedding_dimension_for_model, infer_capability

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
def list_profiles(ctx: AuthContext = Depends(require_organization), db: Session = Depends(get_db)) -> dict:
    ensure_default_profiles(db, ctx.organization_id)
    db.commit()
    chat_profiles = list(
        db.scalars(
            select(ModelProfile)
            .where(
                ModelProfile.organization_id == ctx.organization_id,
                ModelProfile.kind == ProfileKind.CHAT,
                ModelProfile.deleted_at.is_(None),
                ~(
                    (ModelProfile.provider_connection_id.is_(None))
                    & (ModelProfile.model_name == "deterministic-local-384")
                ),
            )
            .order_by(ModelProfile.is_default.desc(), ModelProfile.created_at)
        )
    )
    embedding_profiles = list(
        db.scalars(
            select(EmbeddingProfile)
            .where(
                EmbeddingProfile.organization_id == ctx.organization_id,
                EmbeddingProfile.deleted_at.is_(None),
            )
            .order_by(EmbeddingProfile.is_active.desc(), EmbeddingProfile.created_at)
        )
    )
    connections = _connections_by_id(db, ctx.organization_id, chat_profiles, embedding_profiles)
    return {
        "chat_profiles": [
            {
                "id": str(profile.id),
                "name": profile.name,
                "model_name": profile.model_name,
                "provider_connection_id": str(profile.provider_connection_id)
                if profile.provider_connection_id
                else None,
                "provider": _provider_for_profile(profile, connections),
                "connection_name": _connection_name(profile.provider_connection_id, connections),
                "supports_streaming": profile.supports_streaming,
                "supports_structured_output": profile.supports_structured_output,
                "context_window": profile.context_window,
                "max_output_tokens": profile.max_output_tokens,
                "is_default": profile.is_default,
                "config": profile.config,
            }
            for profile in chat_profiles
        ],
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
                select(CleanupProfile).where(
                    CleanupProfile.organization_id == ctx.organization_id,
                    CleanupProfile.deleted_at.is_(None),
                )
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
                select(ChunkingProfile).where(
                    ChunkingProfile.organization_id == ctx.organization_id,
                    ChunkingProfile.deleted_at.is_(None),
                )
            )
        ],
        "embedding_profiles": [
            {
                "id": str(profile.id),
                "name": profile.name,
                "provider": profile.provider.value,
                "provider_connection_id": str(profile.provider_connection_id)
                if profile.provider_connection_id
                else None,
                "connection_name": _connection_name(profile.provider_connection_id, connections),
                "model_name": profile.model_name,
                "embedding_dimension": profile.embedding_dimension,
                "batch_size": profile.batch_size,
                "rate_limit_per_minute": profile.rate_limit_per_minute,
                "normalization": profile.normalization,
                "is_active": profile.is_active,
                "config": profile.config,
            }
            for profile in embedding_profiles
        ],
    }


@router.post("/chat")
def create_chat_profile(
    payload: ModelProfileCreateIn,
    ctx: AuthContext = Depends(capability("add_provider_keys")),
    db: Session = Depends(get_db),
) -> dict:
    connection = _get_connection(db, ctx.organization_id, payload.provider_connection_id)
    if payload.provider_connection_id and not connection:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Provider connection not found.")
    if not connection and payload.model_name != "deterministic-local-384":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Remote models require a provider connection.")
    provider = connection.provider.value if connection else ProviderKind.LOCAL.value
    capability = infer_capability(provider, payload.model_name)
    if not capability.supports_chat:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Selected model does not support chat.")
    if payload.is_default:
        _clear_default_chat_profiles(db, ctx.organization_id)
    profile = ModelProfile(
        organization_id=ctx.organization_id,
        provider_connection_id=payload.provider_connection_id,
        kind=ProfileKind.CHAT,
        name=payload.name,
        model_name=payload.model_name,
        supports_streaming=payload.supports_streaming,
        supports_embeddings=False,
        supports_structured_output=payload.supports_structured_output,
        context_window=payload.context_window,
        max_output_tokens=payload.max_output_tokens,
        config={
            **payload.config,
            "provider": provider,
        },
        is_default=payload.is_default,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"id": str(profile.id), "message": "Chat model profile created."}


@router.post("/embeddings")
def create_embedding_profile(
    payload: EmbeddingProfileCreateIn,
    ctx: AuthContext = Depends(capability("add_provider_keys")),
    db: Session = Depends(get_db),
) -> dict:
    connection = _get_connection(db, ctx.organization_id, payload.provider_connection_id)
    provider = connection.provider if connection else ProviderKind.LOCAL
    if provider not in {ProviderKind.LOCAL, ProviderKind.OPENAI}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only Local and OpenAI embedding profiles are supported by this deployment.",
        )
    if provider == ProviderKind.LOCAL and payload.model_name != "deterministic-local-384":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Local embeddings use deterministic-local-384.")
    if provider == ProviderKind.LOCAL and payload.embedding_dimension != 384:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Local embeddings are 384-dimensional.")
    if provider != ProviderKind.LOCAL:
        inferred_dimension = embedding_dimension_for_model(provider.value, payload.model_name)
        if inferred_dimension is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Selected model does not support embeddings.")
        if inferred_dimension != payload.embedding_dimension:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"{payload.model_name} is expected to return {inferred_dimension} dimensions.",
            )
    if payload.is_active:
        for profile in db.scalars(
            select(EmbeddingProfile).where(
                EmbeddingProfile.organization_id == ctx.organization_id,
                EmbeddingProfile.deleted_at.is_(None),
            )
        ):
            profile.is_active = False
    profile = EmbeddingProfile(
        organization_id=ctx.organization_id,
        provider_connection_id=payload.provider_connection_id,
        name=payload.name,
        provider=provider,
        model_name=payload.model_name,
        embedding_dimension=payload.embedding_dimension,
        batch_size=payload.batch_size,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        normalization=payload.normalization,
        is_active=payload.is_active,
        config=payload.config,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"id": str(profile.id), "message": "Embedding profile created."}


def _connections_by_id(
    db: Session,
    organization_id,
    chat_profiles: list[ModelProfile],
    embedding_profiles: list[EmbeddingProfile],
) -> dict:
    ids = {
        profile.provider_connection_id
        for profile in [*chat_profiles, *embedding_profiles]
        if profile.provider_connection_id
    }
    if not ids:
        return {}
    return {
        connection.id: connection
        for connection in db.scalars(
            select(ProviderConnection).where(
                ProviderConnection.organization_id == organization_id,
                ProviderConnection.id.in_(ids),
                ProviderConnection.deleted_at.is_(None),
            )
        )
    }


def _connection_name(connection_id, connections: dict) -> str | None:
    if not connection_id or connection_id not in connections:
        return None
    return connections[connection_id].name


def _provider_for_profile(profile: ModelProfile, connections: dict) -> str:
    if profile.provider_connection_id and profile.provider_connection_id in connections:
        return connections[profile.provider_connection_id].provider.value
    return str(profile.config.get("provider") or ProviderKind.LOCAL.value)


def _get_connection(
    db: Session,
    organization_id,
    connection_id,
) -> ProviderConnection | None:
    if not connection_id:
        return None
    connection = db.get(ProviderConnection, connection_id)
    if (
        not connection
        or connection.organization_id != organization_id
        or connection.deleted_at is not None
        or not connection.is_enabled
    ):
        return None
    return connection


def _clear_default_chat_profiles(db: Session, organization_id) -> None:
    for profile in db.scalars(
        select(ModelProfile).where(
            ModelProfile.organization_id == organization_id,
            ModelProfile.kind == ProfileKind.CHAT,
            ModelProfile.deleted_at.is_(None),
        )
    ):
        profile.is_default = False
