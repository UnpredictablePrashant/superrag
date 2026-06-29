from __future__ import annotations

from enum import StrEnum

from fastapi import HTTPException, status


class Role(StrEnum):
    OWNER = "Owner"
    ADMIN = "Admin"
    EDITOR = "Editor"
    MEMBER = "Member"
    VIEWER = "Viewer"


ROLE_RANK = {
    Role.VIEWER: 10,
    Role.MEMBER: 20,
    Role.EDITOR: 30,
    Role.ADMIN: 40,
    Role.OWNER: 50,
}

CAPABILITIES: dict[str, set[Role]] = {
    "manage_settings": {Role.OWNER, Role.ADMIN},
    "add_provider_keys": {Role.OWNER, Role.ADMIN},
    "invite_users": {Role.OWNER, Role.ADMIN},
    "create_knowledge_bases": {Role.OWNER, Role.ADMIN, Role.EDITOR},
    "upload_documents": {Role.OWNER, Role.ADMIN, Role.EDITOR, Role.MEMBER},
    "edit_cleanup_policies": {Role.OWNER, Role.ADMIN, Role.EDITOR},
    "run_ingestion": {Role.OWNER, Role.ADMIN, Role.EDITOR},
    "chat": {Role.OWNER, Role.ADMIN, Role.EDITOR, Role.MEMBER, Role.VIEWER},
    "manage_org_connectors": {Role.OWNER, Role.ADMIN},
    "manage_own_connectors": {Role.OWNER, Role.ADMIN, Role.EDITOR, Role.MEMBER},
    "use_live_tools": {Role.OWNER, Role.ADMIN, Role.EDITOR, Role.MEMBER, Role.VIEWER},
    "view_audit_logs": {Role.OWNER, Role.ADMIN},
}


def require_capability(role: str, capability: str) -> None:
    normalized = Role(role)
    if normalized not in CAPABILITIES[capability]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )


def can_manage_role(actor_role: str, target_role: str) -> bool:
    return ROLE_RANK[Role(actor_role)] > ROLE_RANK[Role(target_role)]
