from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.entities import ModelProfile, ProfileKind, ProviderConnection, ProviderKind
from app.services.chat import ChatModelConfig
from app.services.profiles import ensure_default_profiles


def resolve_chat_model(
    db: Session,
    organization_id: UUID,
    profile_id: UUID | None = None,
) -> ChatModelConfig:
    ensure_default_profiles(db, organization_id)
    db.flush()
    profile = None
    if profile_id:
        profile = _get_chat_profile(db, organization_id, profile_id)
    if not profile:
        profile = db.scalar(
            select(ModelProfile)
            .where(
                ModelProfile.organization_id == organization_id,
                ModelProfile.kind == ProfileKind.CHAT,
                ModelProfile.deleted_at.is_(None),
                ModelProfile.is_default.is_(True),
            )
            .order_by(ModelProfile.created_at)
        )
    if not profile:
        return ChatModelConfig(provider="Local", model_name="deterministic-local-384")
    if not profile.provider_connection_id:
        return ChatModelConfig(
            provider=str(profile.config.get("provider") or "Local"),
            model_name=profile.model_name,
            profile_id=str(profile.id),
            max_output_tokens=profile.max_output_tokens,
            config=profile.config,
        )
    connection = db.get(ProviderConnection, profile.provider_connection_id)
    if (
        not connection
        or connection.organization_id != organization_id
        or connection.deleted_at is not None
        or not connection.is_enabled
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Chat provider connection is not available.")
    api_key = decrypt_secret(connection.encrypted_api_key) if connection.encrypted_api_key else None
    return ChatModelConfig(
        provider=connection.provider.value,
        model_name=profile.model_name,
        api_key=api_key,
        base_url=connection.base_url,
        profile_id=str(profile.id),
        connection_name=connection.name,
        max_output_tokens=profile.max_output_tokens,
        config=profile.config,
    )


def get_openai_connection(db: Session, organization_id: UUID) -> tuple[str, str | None] | None:
    connection = db.scalar(
        select(ProviderConnection)
        .where(
            ProviderConnection.organization_id == organization_id,
            ProviderConnection.provider == ProviderKind.OPENAI,
            ProviderConnection.deleted_at.is_(None),
            ProviderConnection.is_enabled.is_(True),
        )
        .order_by(ProviderConnection.created_at)
    )
    if not connection or not connection.encrypted_api_key:
        return None
    return decrypt_secret(connection.encrypted_api_key), connection.base_url


def _get_chat_profile(db: Session, organization_id: UUID, profile_id: UUID) -> ModelProfile:
    profile = db.get(ModelProfile, profile_id)
    if (
        not profile
        or profile.organization_id != organization_id
        or profile.kind != ProfileKind.CHAT
        or profile.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat model profile not found.")
    return profile
