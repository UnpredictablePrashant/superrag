from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.db.session import get_db
from app.models.entities import ProviderConnection
from app.schemas.api import (
    ProviderConnectionCreateIn,
    ProviderConnectionOut,
    ProviderConnectionPatchIn,
)
from app.services.providers import (
    DEFAULT_CAPABILITIES,
    default_capabilities_for_provider,
    discover_provider_models,
    infer_capability,
    test_provider_connection,
)

router = APIRouter(prefix="/provider-connections", tags=["provider-connections"])


@router.get("", response_model=list[ProviderConnectionOut])
def list_connections(
    ctx: AuthContext = Depends(capability("add_provider_keys")), db: Session = Depends(get_db)
) -> list[ProviderConnection]:
    return list(
        db.scalars(
            select(ProviderConnection).where(
                ProviderConnection.organization_id == ctx.organization_id,
                ProviderConnection.deleted_at.is_(None),
            )
        )
    )


@router.post("", response_model=ProviderConnectionOut)
def create_connection(
    payload: ProviderConnectionCreateIn,
    ctx: AuthContext = Depends(capability("add_provider_keys")),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    connection = ProviderConnection(
        organization_id=ctx.organization_id,
        provider=payload.provider,
        name=payload.name,
        encrypted_api_key=encrypt_secret(payload.api_key) if payload.api_key else None,
        masked_api_key=mask_secret(payload.api_key) if payload.api_key else None,
        base_url=payload.base_url,
        config=payload.config,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.get("/capabilities")
def capabilities() -> list[dict]:
    return [capability.__dict__ for capability in DEFAULT_CAPABILITIES]


@router.get("/models")
async def available_models(
    refresh: bool = Query(default=False),
    ctx: AuthContext = Depends(capability("add_provider_keys")),
    db: Session = Depends(get_db),
) -> list[dict]:
    updated_cache = False
    options = [
        _capability_option(capability)
        for capability in default_capabilities_for_provider("Local")
    ]
    connections = list(
        db.scalars(
            select(ProviderConnection).where(
                ProviderConnection.organization_id == ctx.organization_id,
                ProviderConnection.deleted_at.is_(None),
                ProviderConnection.is_enabled.is_(True),
            )
        )
    )
    for connection in connections:
        api_key = decrypt_secret(connection.encrypted_api_key) if connection.encrypted_api_key else ""
        cached_models = [
            str(model)
            for model in (connection.config or {}).get("available_models", [])
            if str(model).strip()
        ]
        if cached_models and not refresh:
            capabilities_for_connection = [
                infer_capability(connection.provider.value, model) for model in cached_models
            ]
        else:
            capabilities_for_connection = await discover_provider_models(
                connection.provider.value,
                api_key,
                connection.base_url,
            )
            connection.config = {
                **(connection.config or {}),
                "available_models": [capability.model for capability in capabilities_for_connection],
                "last_model_sync_status": "ok",
            }
            updated_cache = True
        options.extend(
            [
                _capability_option(capability, connection)
                for capability in capabilities_for_connection
            ]
        )
    if refresh or updated_cache:
        db.commit()
    return options


@router.patch("/{connection_id}", response_model=ProviderConnectionOut)
def patch_connection(
    connection_id: UUID,
    payload: ProviderConnectionPatchIn,
    ctx: AuthContext = Depends(capability("add_provider_keys")),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    connection = _get_connection(db, ctx.organization_id, connection_id)
    if payload.name is not None:
        connection.name = payload.name
    if payload.api_key is not None:
        connection.encrypted_api_key = encrypt_secret(payload.api_key)
        connection.masked_api_key = mask_secret(payload.api_key)
        connection.status = "rotated"
    if payload.base_url is not None:
        connection.base_url = payload.base_url
    if payload.is_enabled is not None:
        connection.is_enabled = payload.is_enabled
    if payload.config is not None:
        connection.config = payload.config
    db.commit()
    db.refresh(connection)
    return connection


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: UUID,
    ctx: AuthContext = Depends(capability("add_provider_keys")),
    db: Session = Depends(get_db),
) -> dict:
    connection = _get_connection(db, ctx.organization_id, connection_id)
    api_key = decrypt_secret(connection.encrypted_api_key) if connection.encrypted_api_key else ""
    result = await test_provider_connection(connection.provider.value, api_key, connection.base_url)
    connection.status = result.get("status", "error")
    if result.get("models"):
        connection.config = {
            **(connection.config or {}),
            "available_models": result["models"],
            "last_model_sync_status": result.get("status", "error"),
            "last_model_count": result.get("model_count", len(result["models"])),
        }
    db.commit()
    return result


@router.delete("/{connection_id}")
def delete_connection(
    connection_id: UUID,
    ctx: AuthContext = Depends(capability("add_provider_keys")),
    db: Session = Depends(get_db),
) -> dict:
    connection = _get_connection(db, ctx.organization_id, connection_id)
    connection.deleted_at = datetime.now(UTC)
    connection.is_enabled = False
    db.commit()
    return {"message": "Provider connection deleted."}


def _get_connection(db: Session, organization_id: UUID, connection_id: UUID) -> ProviderConnection:
    connection = db.get(ProviderConnection, connection_id)
    if not connection or connection.organization_id != organization_id or connection.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Provider connection not found.")
    return connection


def _capability_option(capability, connection: ProviderConnection | None = None) -> dict:
    return {
        "provider_connection_id": str(connection.id) if connection else None,
        "connection_name": connection.name if connection else "Local",
        "provider": capability.provider,
        "model": capability.model,
        "supports_chat": capability.supports_chat,
        "supports_streaming": capability.supports_streaming,
        "supports_embeddings": capability.supports_embeddings,
        "supports_structured_output": capability.supports_structured_output,
        "maximum_context_window": capability.maximum_context_window,
        "maximum_output_tokens": capability.maximum_output_tokens,
        "embedding_dimension": capability.embedding_dimension,
        "status": capability.status,
    }
