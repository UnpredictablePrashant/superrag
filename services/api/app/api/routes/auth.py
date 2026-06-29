from __future__ import annotations

from datetime import UTC, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, request_meta
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.security import (
    create_session_token,
    generate_otp,
    hash_secret,
    utcnow,
    verify_secret,
)
from app.db.session import get_db
from app.models.entities import (
    MemberRole,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    OTPCode,
    User,
)
from app.models.entities import (
    Session as UserSession,
)
from app.schemas.api import AuthResponse, RequestOTPIn, UserOut, VerifyOTPIn
from app.services.email import send_otp_email
from app.services.profiles import ensure_default_profiles

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-otp", response_model=AuthResponse)
def request_otp(payload: RequestOTPIn, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.lower()
    enforce_rate_limit(f"otp:{email}", limit=5, window_seconds=60)
    latest = db.scalar(select(OTPCode).where(OTPCode.email == email).order_by(OTPCode.created_at.desc()))
    if latest and latest.created_at.replace(tzinfo=UTC) > utcnow() - timedelta(
        seconds=settings.otp_resend_cooldown_seconds
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {settings.otp_resend_cooldown_seconds} seconds before requesting another code.",
        )
    code = generate_otp()
    otp = OTPCode(
        email=email,
        code_hash=hash_secret(code),
        expires_at=utcnow() + timedelta(minutes=settings.otp_ttl_minutes),
        request_ip=request.client.host if request.client else None,
    )
    db.add(otp)
    db.commit()
    send_otp_email(email, code)
    return AuthResponse(
        message="OTP sent.",
        dev_code=code if settings.allow_dev_auth_codes and settings.app_env != "production" else None,
    )


@router.post("/verify-otp", response_model=AuthResponse)
def verify_otp(
    payload: VerifyOTPIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    email = payload.email.lower()
    otp = db.scalar(
        select(OTPCode)
        .where(OTPCode.email == email, OTPCode.consumed_at.is_(None))
        .order_by(OTPCode.created_at.desc())
    )
    if not otp or otp.expires_at.replace(tzinfo=UTC) < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="OTP has expired. Request a new code.")
    if otp.attempts >= settings.otp_max_attempts:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many OTP attempts.")
    otp.attempts += 1
    if not verify_secret(payload.code, otp.code_hash):
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")
    otp.consumed_at = utcnow()

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(email=email, is_email_verified=True)
        db.add(user)
        db.flush()
    user.is_email_verified = True
    user.last_login_at = utcnow()

    if payload.invitation_token:
        _accept_invitation(db, payload.invitation_token, user)

    membership = db.scalar(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id, OrganizationMember.status == "active")
        .order_by(OrganizationMember.created_at)
    )
    if not membership and payload.organization_name:
        organization = _create_organization(db, payload.organization_name, user.id)
        membership = OrganizationMember(
            organization_id=organization.id, user_id=user.id, role=MemberRole.OWNER, status="active"
        )
        db.add(membership)
        ensure_default_profiles(db, organization.id)
        db.flush()

    organization = db.get(Organization, membership.organization_id) if membership else None
    token = create_session_token(user.id, organization.id if organization else None, membership.role.value if membership else None)
    db.add(
        UserSession(
            user_id=user.id,
            organization_id=organization.id if organization else None,
            token_hash=hash_secret(token),
            expires_at=utcnow() + timedelta(minutes=settings.session_ttl_minutes),
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    )
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
    return AuthResponse(
        user=UserOut.model_validate(user),
        organization=organization,
        role=membership.role if membership else None,
        needs_onboarding=membership is None,
        message="Signed in.",
    )


@router.post("/logout", response_model=AuthResponse)
def logout(
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AuthResponse:
    ctx.session.revoked_at = utcnow()
    ip, user_agent = request_meta(request)
    ctx.session.ip_address = ctx.session.ip_address or ip
    ctx.session.user_agent = ctx.session.user_agent or user_agent
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return AuthResponse(message="Signed out.")


@router.get("/me", response_model=AuthResponse)
def me(ctx: AuthContext = Depends(get_auth_context)) -> AuthResponse:
    return AuthResponse(
        user=UserOut.model_validate(ctx.user),
        organization=ctx.organization,
        role=MemberRole(ctx.role) if ctx.role else None,
        needs_onboarding=ctx.organization is None,
    )


def _create_organization(db: Session, name: str, owner_id: UUID) -> Organization:
    base_slug = _slugify(name)
    slug = base_slug
    counter = 2
    while db.scalar(select(Organization).where(Organization.slug == slug)):
        slug = f"{base_slug}-{counter}"
        counter += 1
    organization = Organization(name=name, slug=slug, settings={"created_by": str(owner_id)})
    db.add(organization)
    db.flush()
    return organization


def _accept_invitation(db: Session, token: str, user: User) -> None:
    invitation = db.scalar(
        select(OrganizationInvitation).where(OrganizationInvitation.token_hash == hash_secret(token))
    )
    if not invitation or invitation.accepted_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid or already accepted.")
    if invitation.expires_at.replace(tzinfo=UTC) < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invitation has expired.")
    if invitation.email.lower() != user.email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invitation email does not match this account.")
    existing = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == invitation.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if not existing:
        db.add(
            OrganizationMember(
                organization_id=invitation.organization_id,
                user_id=user.id,
                role=invitation.role,
                status="active",
            )
        )
    invitation.accepted_at = utcnow()


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "organization"
