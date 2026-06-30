from __future__ import annotations

from datetime import UTC
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_secret, utcnow
from app.models.entities import OrganizationInvitation, OrganizationMember, User


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

    invitation.accepted_at = utcnow()
    db.flush()
    return membership
