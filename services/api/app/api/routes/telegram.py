from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability
from app.core.config import settings
from app.core.security import encrypt_secret, mask_secret
from app.db.session import get_db
from app.models.entities import TelegramAllowedUser, TelegramIntegration, TelegramMessageLog
from app.schemas.api import (
    TelegramAllowedUserCreateIn,
    TelegramAllowedUserOut,
    TelegramAllowedUserPatchIn,
    TelegramIntegrationOut,
    TelegramIntegrationPatchIn,
    TelegramMessageLogOut,
)
from app.services.telegram import (
    build_webhook_url,
    process_telegram_update,
    record_telegram_update_receipt,
    register_telegram_webhook,
    test_telegram_bot,
)
from app.workers.tasks import process_telegram_update_task

router = APIRouter(prefix="/integrations/telegram", tags=["telegram"])


@router.get("", response_model=TelegramIntegrationOut)
def get_integration(
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> TelegramIntegrationOut:
    integration = _ensure_integration(db, ctx.organization_id)
    db.commit()
    db.refresh(integration)
    return _integration_out(integration)


@router.patch("", response_model=TelegramIntegrationOut)
def patch_integration(
    payload: TelegramIntegrationPatchIn,
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> TelegramIntegrationOut:
    integration = _ensure_integration(db, ctx.organization_id)
    if payload.bot_token is not None:
        integration.encrypted_bot_token = encrypt_secret(payload.bot_token)
        integration.masked_bot_token = mask_secret(payload.bot_token)
    for field in (
        "bot_username",
        "default_knowledge_base_id",
        "default_chat_model_profile_id",
        "default_cleanup_profile_id",
        "default_chunking_profile_id",
        "default_embedding_profile_id",
        "auto_ingest_text",
        "auto_ingest_documents",
        "auto_ingest_voice",
        "is_enabled",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(integration, field, value)
    if payload.config is not None:
        integration.config = payload.config
    db.commit()
    db.refresh(integration)
    return _integration_out(integration)


@router.post("/test")
def test_integration(
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> dict:
    integration = _get_existing_integration(db, ctx.organization_id)
    result = test_telegram_bot(integration)
    integration.bot_username = result.get("username") or integration.bot_username
    db.commit()
    return {"status": "ok", "bot": result}


@router.post("/register-webhook")
def register_webhook(
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> dict:
    integration = _get_existing_integration(db, ctx.organization_id)
    webhook_url = build_webhook_url(settings.api_base_url, integration.id)
    result = register_telegram_webhook(integration, webhook_url)
    integration.config = {**(integration.config or {}), "webhook_registered_at": datetime.now(UTC).isoformat()}
    db.commit()
    return {"status": "ok", "webhook_url": webhook_url, "telegram": result}


@router.get("/allowed-users", response_model=list[TelegramAllowedUserOut])
def list_allowed_users(
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> list[TelegramAllowedUser]:
    integration = _ensure_integration(db, ctx.organization_id)
    return list(
        db.scalars(
            select(TelegramAllowedUser)
            .where(
                TelegramAllowedUser.integration_id == integration.id,
                TelegramAllowedUser.deleted_at.is_(None),
            )
            .order_by(TelegramAllowedUser.created_at.desc())
        )
    )


@router.post("/allowed-users", response_model=TelegramAllowedUserOut)
def create_allowed_user(
    payload: TelegramAllowedUserCreateIn,
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> TelegramAllowedUser:
    integration = _ensure_integration(db, ctx.organization_id)
    if not (payload.telegram_user_id or payload.username or payload.phone_number):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Add a username, phone number, or Telegram user id.")
    allowed = TelegramAllowedUser(
        organization_id=ctx.organization_id,
        integration_id=integration.id,
        user_id=payload.user_id,
        telegram_user_id=payload.telegram_user_id,
        username=_normalize_username(payload.username),
        phone_number=_normalize_phone(payload.phone_number),
        display_name=payload.display_name,
        can_ingest=payload.can_ingest,
        can_query=payload.can_query,
    )
    db.add(allowed)
    db.commit()
    db.refresh(allowed)
    return allowed


@router.patch("/allowed-users/{allowed_user_id}", response_model=TelegramAllowedUserOut)
def patch_allowed_user(
    allowed_user_id: UUID,
    payload: TelegramAllowedUserPatchIn,
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> TelegramAllowedUser:
    integration = _ensure_integration(db, ctx.organization_id)
    allowed = _get_allowed_user(db, integration.id, allowed_user_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "username":
            value = _normalize_username(value)
        if field == "phone_number":
            value = _normalize_phone(value)
        setattr(allowed, field, value)
    db.commit()
    db.refresh(allowed)
    return allowed


@router.delete("/allowed-users/{allowed_user_id}")
def delete_allowed_user(
    allowed_user_id: UUID,
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> dict:
    integration = _ensure_integration(db, ctx.organization_id)
    allowed = _get_allowed_user(db, integration.id, allowed_user_id)
    allowed.deleted_at = datetime.now(UTC)
    allowed.is_enabled = False
    db.commit()
    return {"message": "Telegram user removed."}


@router.get("/messages", response_model=list[TelegramMessageLogOut])
def list_messages(
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> list[TelegramMessageLog]:
    integration = _ensure_integration(db, ctx.organization_id)
    return list(
        db.scalars(
            select(TelegramMessageLog)
            .where(TelegramMessageLog.integration_id == integration.id)
            .order_by(TelegramMessageLog.created_at.desc())
            .limit(100)
        )
    )


@router.post("/webhook/{integration_id}")
async def telegram_webhook(
    integration_id: UUID,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    integration = db.get(TelegramIntegration, integration_id)
    if (
        not integration
        or integration.deleted_at is not None
        or not integration.is_enabled
        or x_telegram_bot_api_secret_token != integration.webhook_secret_token
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram webhook.")
    payload = await request.json()
    record_telegram_update_receipt(db, integration, payload)
    db.commit()
    try:
        process_telegram_update_task.delay(str(integration.id), payload)
    except Exception:
        process_telegram_update(db, integration, payload)
    return {"ok": True}


def _ensure_integration(db: Session, organization_id: UUID) -> TelegramIntegration:
    integration = db.scalar(
        select(TelegramIntegration).where(
            TelegramIntegration.organization_id == organization_id,
            TelegramIntegration.deleted_at.is_(None),
        )
    )
    if integration:
        return integration
    integration = TelegramIntegration(
        organization_id=organization_id,
        webhook_secret_token=secrets.token_urlsafe(32),
        is_enabled=False,
    )
    db.add(integration)
    db.flush()
    return integration


def _get_existing_integration(db: Session, organization_id: UUID) -> TelegramIntegration:
    integration = _ensure_integration(db, organization_id)
    if not integration.encrypted_bot_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Telegram bot token is not configured.")
    return integration


def _get_allowed_user(db: Session, integration_id: UUID, allowed_user_id: UUID) -> TelegramAllowedUser:
    allowed = db.get(TelegramAllowedUser, allowed_user_id)
    if not allowed or allowed.integration_id != integration_id or allowed.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Telegram allowed user not found.")
    return allowed


def _integration_out(integration: TelegramIntegration) -> TelegramIntegrationOut:
    return TelegramIntegrationOut(
        id=integration.id,
        bot_username=integration.bot_username,
        masked_bot_token=integration.masked_bot_token,
        webhook_secret_token=integration.webhook_secret_token,
        webhook_url=build_webhook_url(settings.api_base_url, integration.id),
        default_knowledge_base_id=integration.default_knowledge_base_id,
        default_chat_model_profile_id=integration.default_chat_model_profile_id,
        default_cleanup_profile_id=integration.default_cleanup_profile_id,
        default_chunking_profile_id=integration.default_chunking_profile_id,
        default_embedding_profile_id=integration.default_embedding_profile_id,
        auto_ingest_text=integration.auto_ingest_text,
        auto_ingest_documents=integration.auto_ingest_documents,
        auto_ingest_voice=integration.auto_ingest_voice,
        is_enabled=integration.is_enabled,
        config=integration.config,
    )


def _normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.strip().lstrip("@").lower() or None


def _normalize_phone(phone_number: str | None) -> str | None:
    if not phone_number:
        return None
    return "".join(ch for ch in phone_number.strip() if ch.isdigit() or ch == "+") or None
