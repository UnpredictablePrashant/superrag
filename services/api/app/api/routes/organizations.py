from __future__ import annotations

import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    AuthContext,
    capability,
    get_auth_context,
    request_meta,
    require_organization,
)
from app.core.config import settings
from app.core.permissions import can_manage_role
from app.core.security import create_session_token, hash_secret, utcnow
from app.db.session import get_db
from app.models.entities import (
    MemberRole,
    Notification,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    TelegramAllowedUser,
    TelegramIntegration,
    User,
)
from app.models.entities import (
    Session as UserSession,
)
from app.schemas.api import (
    InvitationCreateIn,
    MemberOut,
    MemberPatchIn,
    OrganizationCreateIn,
    OrganizationOut,
    OrganizationPatchIn,
)
from app.services.audit import write_audit_log
from app.services.email import send_invitation_email
from app.services.invitations import accept_organization_invitation
from app.services.profiles import ensure_default_profiles

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/current", response_model=OrganizationOut)
def get_current_organization(ctx: AuthContext = Depends(require_organization)) -> Organization:
    return ctx.organization


@router.post("/current", response_model=OrganizationOut)
def create_current_organization(
    payload: OrganizationCreateIn,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Organization:
    if ctx.organization:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A current organization already exists.")
    organization = _create_organization(db, payload.name)
    db.add(OrganizationMember(organization_id=organization.id, user_id=ctx.user.id, role=MemberRole.OWNER))
    ensure_default_profiles(db, organization.id)
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=organization.id,
        actor_user_id=ctx.user.id,
        action="organization.created",
        resource_type="organization",
        resource_id=str(organization.id),
        ip_address=ip,
        user_agent=ua,
    )
    token = create_session_token(ctx.user.id, organization.id, MemberRole.OWNER.value)
    db.add(
        UserSession(
            user_id=ctx.user.id,
            organization_id=organization.id,
            token_hash=hash_secret(token),
            expires_at=utcnow() + timedelta(minutes=settings.session_ttl_minutes),
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    )
    ctx.session.revoked_at = utcnow()
    db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )
    db.refresh(organization)
    return organization


@router.patch("/current", response_model=OrganizationOut)
def patch_current_organization(
    payload: OrganizationPatchIn,
    request: Request,
    ctx: AuthContext = Depends(capability("manage_settings")),
    db: Session = Depends(get_db),
) -> Organization:
    organization = ctx.organization
    if payload.name:
        organization.name = payload.name
    if payload.settings is not None:
        organization.settings = {**organization.settings, **payload.settings}
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="organization.updated",
        resource_type="organization",
        resource_id=str(organization.id),
        metadata=payload.model_dump(exclude_none=True),
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(organization)
    return organization


@router.post("/invitations")
def create_invitation(
    payload: InvitationCreateIn,
    request: Request,
    ctx: AuthContext = Depends(capability("invite_users")),
    db: Session = Depends(get_db),
) -> dict:
    if not can_manage_role(ctx.role or "", payload.role.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You cannot invite users with this role.")
    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        organization_id=ctx.organization_id,
        email=payload.email.lower(),
        role=payload.role,
        token_hash=hash_secret(token),
        invited_by_user_id=ctx.user.id,
        telegram_user_id=payload.telegram_user_id,
        telegram_username=_normalize_telegram_username(payload.telegram_username),
        telegram_phone_number=_normalize_phone(payload.telegram_phone_number),
        telegram_can_ingest=payload.telegram_can_ingest,
        telegram_can_query=payload.telegram_can_query,
        expires_at=utcnow() + timedelta(days=14),
    )
    db.add(invitation)
    db.add(
        Notification(
            organization_id=ctx.organization_id,
            user_id=None,
            kind="invitation_sent",
            title="Invitation sent",
            body=f"{payload.email} was invited as {payload.role.value}.",
            severity="info",
            metadata_json={"email": payload.email},
        )
    )
    ip, ua = request_meta(request)
    write_audit_log(
        db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        action="organization.invitation_created",
        resource_type="organization_invitation",
        metadata={"email": payload.email, "role": payload.role.value},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()
    from app.core.config import settings

    invite_url = f"{settings.web_base_url}/invite/{token}"
    send_invitation_email(payload.email, ctx.organization.name, invite_url)
    return {"message": "Invitation sent.", "invite_url": invite_url}


@router.post("/invitations/{token}/accept")
def accept_invitation(
    token: str,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    membership = accept_organization_invitation(db, token, ctx.user)
    organization = db.get(Organization, membership.organization_id)
    db.add(
        Notification(
            organization_id=membership.organization_id,
            user_id=None,
            kind="team_member_joined",
            title="Team member joined",
            body=f"{ctx.user.email} joined the organization.",
            severity="success",
            metadata_json={"user_id": str(ctx.user.id)},
        )
    )
    session_token = create_session_token(ctx.user.id, membership.organization_id, membership.role.value)
    db.add(
        UserSession(
            user_id=ctx.user.id,
            organization_id=membership.organization_id,
            token_hash=hash_secret(session_token),
            expires_at=utcnow() + timedelta(minutes=settings.session_ttl_minutes),
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    )
    ctx.session.revoked_at = utcnow()
    db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )
    return {"message": "Invitation accepted.", "organization": OrganizationOut.model_validate(organization)}


@router.get("/members", response_model=list[MemberOut])
def list_members(ctx: AuthContext = Depends(require_organization), db: Session = Depends(get_db)) -> list[MemberOut]:
    rows = db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == ctx.organization_id)
        .order_by(OrganizationMember.created_at)
    ).all()
    return [_member_out(member, user) for member, user in rows]


@router.patch("/members/{member_id}", response_model=MemberOut)
def patch_member(
    member_id: str,
    payload: MemberPatchIn,
    ctx: AuthContext = Depends(capability("invite_users")),
    db: Session = Depends(get_db),
) -> MemberOut:
    member = db.get(OrganizationMember, member_id)
    if not member or member.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found.")
    if not can_manage_role(ctx.role or "", member.role.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You cannot change this member.")
    user = db.scalar(select(User).where(User.id == member.user_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member user not found.")

    fields = payload.model_dump(exclude_unset=True)
    if "email" in fields and payload.email is not None:
        next_email = str(payload.email).lower()
        existing_user = db.scalar(select(User).where(User.email == next_email, User.id != user.id))
        if existing_user:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="That email address is already in use.")
        user.email = next_email
    if "full_name" in fields:
        user.full_name = _clean_optional_text(payload.full_name)
    if "phone_number" in fields:
        user.phone_number = _normalize_phone(payload.phone_number)
    if "telegram_username" in fields:
        user.telegram_username = _normalize_telegram_username(payload.telegram_username)
    if payload.role:
        member.role = payload.role
    if payload.status:
        member.status = payload.status
    if "full_name" in fields or "phone_number" in fields or "telegram_username" in fields:
        _sync_member_telegram_allowed_user(db, ctx.organization_id, user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Member details conflict with an existing user.") from exc
    db.refresh(member)
    db.refresh(user)
    return _member_out(member, user)


def _member_out(member: OrganizationMember, user: User | None) -> MemberOut:
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        email=user.email if user else None,
        full_name=user.full_name if user else None,
        phone_number=user.phone_number if user else None,
        telegram_username=user.telegram_username if user else None,
        role=member.role,
        status=member.status,
        chat_status=member.chat_status,
        status_message=member.status_message,
        status_updated_at=member.status_updated_at,
        created_at=member.created_at,
    )


def _sync_member_telegram_allowed_user(db: Session, organization_id, user: User) -> None:
    username = _normalize_telegram_username(user.telegram_username)
    phone_number = _normalize_phone(user.phone_number)
    integration = db.scalar(
        select(TelegramIntegration).where(
            TelegramIntegration.organization_id == organization_id,
            TelegramIntegration.deleted_at.is_(None),
        )
    )
    if not integration:
        if not (username or phone_number):
            return
        integration = TelegramIntegration(
            organization_id=organization_id,
            webhook_secret_token=secrets.token_urlsafe(32),
            is_enabled=False,
        )
        db.add(integration)
        db.flush()

    allowed = db.scalar(
        select(TelegramAllowedUser).where(
            TelegramAllowedUser.integration_id == integration.id,
            TelegramAllowedUser.user_id == user.id,
            TelegramAllowedUser.deleted_at.is_(None),
        )
    )
    _ensure_telegram_identifier_available(db, integration.id, username, phone_number, allowed)
    if not allowed:
        if not (username or phone_number):
            return
        db.add(
            TelegramAllowedUser(
                organization_id=organization_id,
                integration_id=integration.id,
                user_id=user.id,
                username=username,
                phone_number=phone_number,
                display_name=user.full_name or user.email,
                can_ingest=True,
                can_query=True,
            )
        )
        return

    allowed.username = username
    allowed.phone_number = phone_number
    allowed.display_name = user.full_name or user.email
    allowed.is_enabled = bool(allowed.telegram_user_id or username or phone_number)


def _ensure_telegram_identifier_available(
    db: Session,
    integration_id,
    username: str | None,
    phone_number: str | None,
    current_allowed: TelegramAllowedUser | None,
) -> None:
    if username:
        existing = db.scalar(
            select(TelegramAllowedUser).where(
                TelegramAllowedUser.integration_id == integration_id,
                TelegramAllowedUser.username == username,
                TelegramAllowedUser.deleted_at.is_(None),
            )
        )
        if existing and (not current_allowed or existing.id != current_allowed.id):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="That Telegram username is already allowed for another user.")
    if phone_number:
        existing = db.scalar(
            select(TelegramAllowedUser).where(
                TelegramAllowedUser.integration_id == integration_id,
                TelegramAllowedUser.phone_number == phone_number,
                TelegramAllowedUser.deleted_at.is_(None),
            )
        )
        if existing and (not current_allowed or existing.id != current_allowed.id):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="That phone number is already allowed for another user.")


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _create_organization(db: Session, name: str) -> Organization:
    base_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "organization"
    slug = base_slug
    counter = 2
    while db.scalar(select(Organization).where(Organization.slug == slug)):
        slug = f"{base_slug}-{counter}"
        counter += 1
    organization = Organization(name=name, slug=slug)
    db.add(organization)
    db.flush()
    return organization


def _normalize_telegram_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.strip().lstrip("@").lower() or None


def _normalize_phone(phone_number: str | None) -> str | None:
    if not phone_number:
        return None
    normalized = re.sub(r"[^\d+]", "", str(phone_number).strip())
    if normalized.startswith("00"):
        normalized = "+" + normalized[2:]
    return normalized or None
