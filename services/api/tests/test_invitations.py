from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.permissions import can_manage_role, require_capability
from app.core.security import utcnow
from app.models.entities import (
    MemberRole,
    OrganizationMember,
    TelegramAllowedUser,
    TelegramIntegration,
)
from app.services.invitations import accept_organization_invitation


class FakeSession:
    def __init__(self, *scalar_results: object) -> None:
        self.scalar_results = list(scalar_results)
        self.added: list[object] = []
        self.flushed = False

    def scalar(self, _query: object) -> object:
        return self.scalar_results.pop(0)

    def add(self, item: object) -> None:
        self.added.append(item)

    def flush(self) -> None:
        for item in self.added:
            if hasattr(item, "id") and item.id is None:
                item.id = uuid4()
        self.flushed = True


def test_accept_invitation_reactivates_existing_removed_membership() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    invitation = SimpleNamespace(
        accepted_at=None,
        email="member@example.com",
        expires_at=utcnow() + timedelta(minutes=5),
        organization_id=organization_id,
        role=MemberRole.MEMBER,
    )
    membership = OrganizationMember(
        organization_id=organization_id,
        user_id=user_id,
        role=MemberRole.VIEWER,
        status="removed",
    )
    db = FakeSession(invitation, membership)
    user = SimpleNamespace(id=user_id, email="member@example.com")

    accepted_membership = accept_organization_invitation(db, "token", user)  # type: ignore[arg-type]

    assert accepted_membership is membership
    assert membership.status == "active"
    assert membership.role == MemberRole.MEMBER
    assert invitation.accepted_at is not None
    assert db.flushed
    assert db.added == []


def test_accept_invitation_keeps_existing_active_member_role() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    invitation = SimpleNamespace(
        accepted_at=None,
        email="member@example.com",
        expires_at=utcnow() + timedelta(minutes=5),
        organization_id=organization_id,
        role=MemberRole.VIEWER,
    )
    membership = OrganizationMember(
        organization_id=organization_id,
        user_id=user_id,
        role=MemberRole.ADMIN,
        status="active",
    )
    db = FakeSession(invitation, membership)
    user = SimpleNamespace(id=user_id, email="member@example.com")

    accepted_membership = accept_organization_invitation(db, "token", user)  # type: ignore[arg-type]

    assert accepted_membership is membership
    assert membership.status == "active"
    assert membership.role == MemberRole.ADMIN
    assert invitation.accepted_at is not None


def test_accept_invitation_creates_active_membership_for_new_member() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    invitation = SimpleNamespace(
        accepted_at=None,
        email="member@example.com",
        expires_at=utcnow() + timedelta(minutes=5),
        organization_id=organization_id,
        role=MemberRole.EDITOR,
    )
    db = FakeSession(invitation, None)
    user = SimpleNamespace(id=user_id, email="member@example.com")

    membership = accept_organization_invitation(db, "token", user)  # type: ignore[arg-type]

    assert membership.organization_id == organization_id
    assert membership.user_id == user_id
    assert membership.status == "active"
    assert membership.role == MemberRole.EDITOR
    assert db.added == [membership]
    assert db.flushed


def test_accept_invitation_links_telegram_allowed_user() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    invitation = SimpleNamespace(
        accepted_at=None,
        email="member@example.com",
        expires_at=utcnow() + timedelta(minutes=5),
        organization_id=organization_id,
        role=MemberRole.MEMBER,
        telegram_user_id=None,
        telegram_username="memberhandle",
        telegram_phone_number="+918800460102",
        telegram_can_ingest=True,
        telegram_can_query=True,
    )
    db = FakeSession(invitation, None, None, None, None)
    user = SimpleNamespace(id=user_id, email="member@example.com", full_name="Member Example")

    membership = accept_organization_invitation(db, "token", user)  # type: ignore[arg-type]

    integration = next(item for item in db.added if isinstance(item, TelegramIntegration))
    allowed = next(item for item in db.added if isinstance(item, TelegramAllowedUser))
    assert membership.user_id == user_id
    assert allowed.organization_id == organization_id
    assert allowed.integration_id == integration.id
    assert allowed.user_id == user_id
    assert allowed.username == "memberhandle"
    assert allowed.phone_number == "+918800460102"
    assert allowed.display_name == "Member Example"


def test_invitation_roles_must_be_below_actor_role() -> None:
    assert can_manage_role(MemberRole.ADMIN.value, MemberRole.MEMBER.value)
    assert not can_manage_role(MemberRole.ADMIN.value, MemberRole.ADMIN.value)
    assert can_manage_role(MemberRole.OWNER.value, MemberRole.ADMIN.value)


def test_non_admin_roles_cannot_invite_users() -> None:
    with pytest.raises(HTTPException):
        require_capability(MemberRole.MEMBER.value, "invite_users")
