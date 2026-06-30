from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.core.security import utcnow
from app.models.entities import MemberRole, OrganizationMember
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
