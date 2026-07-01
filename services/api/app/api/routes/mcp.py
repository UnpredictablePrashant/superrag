from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, request_meta, require_organization
from app.core.config import settings
from app.core.security import create_session_token, hash_secret, utcnow
from app.db.session import get_db
from app.models.entities import Session as UserSession

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("/setup")
def create_mcp_setup(
    request: Request,
    client: Literal["cursor", "claude", "generic"] = "generic",
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    token = create_session_token(ctx.user.id, ctx.organization_id, ctx.role)
    expires_at = utcnow() + timedelta(minutes=settings.session_ttl_minutes)
    ip, user_agent = request_meta(request)
    db.add(
        UserSession(
            user_id=ctx.user.id,
            organization_id=ctx.organization_id,
            token_hash=hash_secret(token),
            expires_at=expires_at,
            user_agent=f"mcp-setup:{client}; {user_agent or 'unknown'}",
            ip_address=ip,
        )
    )
    db.commit()
    mcp_url = f"{settings.api_base_url.rstrip('/')}/mcp"
    config = {
        "mcpServers": {
            "rag-console": {
                "type": "http",
                "url": mcp_url,
                "headers": {
                    "Authorization": f"Bearer {token}",
                },
            }
        }
    }
    return {
        "mcp_url": mcp_url,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "server_name": "rag-console",
        "cursor_config": config,
        "claude_config": config,
        "generic_config": config,
    }
