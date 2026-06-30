from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import require_capability
from app.core.security import decode_session_token, hash_secret
from app.db.session import get_db
from app.models.entities import Organization, OrganizationMember, User
from app.models.entities import Session as UserSession
from app.services.invitations import find_active_membership


@dataclass(frozen=True)
class AuthContext:
    user: User
    organization: Organization | None
    role: str | None
    session: UserSession

    @property
    def organization_id(self) -> UUID:
        if not self.organization:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Create or select an organization first.")
        return self.organization.id


def get_auth_context(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> AuthContext:
    if not session_cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    try:
        payload = decode_session_token(session_cookie)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.") from exc

    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == hash_secret(session_cookie))
    )
    if not session or session.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Session has ended.")
    user = db.get(User, UUID(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    organization = None
    role = None
    org_claim = payload.get("org")
    if org_claim:
        membership = db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == UUID(org_claim),
                OrganizationMember.user_id == user.id,
                OrganizationMember.status == "active",
            )
        )
        if membership:
            organization = db.get(Organization, membership.organization_id)
            role = membership.role.value
    if not organization:
        membership = find_active_membership(db, user.id)
        if membership:
            organization = db.get(Organization, membership.organization_id)
            role = membership.role.value

    return AuthContext(user=user, organization=organization, role=role, session=session)


def require_organization(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    _ = ctx.organization_id
    if not ctx.role:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Organization membership is required.")
    return ctx


def capability(capability_name: str):
    def dependency(ctx: AuthContext = Depends(require_organization)) -> AuthContext:
        require_capability(ctx.role or "", capability_name)
        return ctx

    return dependency


def request_meta(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get("user-agent")
