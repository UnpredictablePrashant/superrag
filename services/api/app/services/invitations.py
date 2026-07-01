from __future__ import annotations

import secrets
from datetime import UTC
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_secret, utcnow
from app.models.entities import (
    OrganizationInvitation,
    OrganizationMember,
    TelegramAllowedUser,
    TelegramIntegration,
    User,
)


def find_active_membership(
    db: Session, user_id: UUID, organization_id: UUID | None = None
) -> OrganizationMember | None:
    query = select(OrganizationMember).where(
        OrganizationMember.user_id == user_id,
        OrganizationMember.status == "active",
    )
    if organization_id:
        query = query.where(OrganizationMember.organization_id == organization_id)
    return db.scalar(query.order_by(OrganizationMember.created_at))


def accept_organization_invitation(db: Session, token: str, user: User) -> OrganizationMember:
    invitation = db.scalar(
        select(OrganizationInvitation).where(OrganizationInvitation.token_hash == hash_secret(token))
    )
    if not invitation or invitation.accepted_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid or already accepted.")
    if invitation.expires_at.replace(tzinfo=UTC) < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invitation has expired.")
    if invitation.email.lower() != user.email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invitation email does not match this account.")

    membership = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == invitation.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if membership:
        if membership.status != "active":
            membership.role = invitation.role
            membership.status = "active"
    else:
        membership = OrganizationMember(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
            status="active",
        )
        db.add(membership)

    _sync_telegram_allowed_user(db, invitation, user)
    invitation.accepted_at = utcnow()
    db.flush()
    return membership


def _sync_telegram_allowed_user(db: Session, invitation: OrganizationInvitation, user: User) -> None:
    telegram_user_id = getattr(invitation, "telegram_user_id", None)
    username = getattr(invitation, "telegram_username", None)
    phone_number = getattr(invitation, "telegram_phone_number", None)
    if not (telegram_user_id or username or phone_number):
        return

    integration = db.scalar(
        select(TelegramIntegration).where(
            TelegramIntegration.organization_id == invitation.organization_id,
            TelegramIntegration.deleted_at.is_(None),
        )
    )
    if not integration:
        integration = TelegramIntegration(
            organization_id=invitation.organization_id,
            webhook_secret_token=secrets.token_urlsafe(32),
            is_enabled=False,
        )
        db.add(integration)
        db.flush()

    allowed = _find_allowed_telegram_user(db, integration.id, telegram_user_id, username, phone_number)
    if not allowed:
        db.add(
            TelegramAllowedUser(
                organization_id=invitation.organization_id,
                integration_id=integration.id,
                user_id=user.id,
                telegram_user_id=telegram_user_id,
                username=username,
                phone_number=phone_number,
                display_name=getattr(user, "full_name", None) or user.email,
                can_ingest=getattr(invitation, "telegram_can_ingest", True),
                can_query=getattr(invitation, "telegram_can_query", True),
            )
        )
        return

    allowed.user_id = user.id
    allowed.display_name = allowed.display_name or getattr(user, "full_name", None) or user.email
    allowed.can_ingest = getattr(invitation, "telegram_can_ingest", True)
    allowed.can_query = getattr(invitation, "telegram_can_query", True)
    allowed.is_enabled = True
    if telegram_user_id and not allowed.telegram_user_id:
        allowed.telegram_user_id = telegram_user_id
    if username and not allowed.username:
        allowed.username = username
    if phone_number and not allowed.phone_number:
        allowed.phone_number = phone_number


def _find_allowed_telegram_user(
    db: Session,
    integration_id: UUID,
    telegram_user_id: int | None,
    username: str | None,
    phone_number: str | None,
) -> TelegramAllowedUser | None:
    clauses = []
    if telegram_user_id:
        clauses.append(TelegramAllowedUser.telegram_user_id == telegram_user_id)
    if username:
        clauses.append(TelegramAllowedUser.username == username)
    if phone_number:
        clauses.append(TelegramAllowedUser.phone_number == phone_number)
    for clause in clauses:
        allowed = db.scalar(
            select(TelegramAllowedUser).where(
                TelegramAllowedUser.integration_id == integration_id,
                TelegramAllowedUser.deleted_at.is_(None),
                clause,
            )
        )
        if allowed:
            return allowed
    return None
