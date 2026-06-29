from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability
from app.db.session import get_db
from app.models.entities import AuditLog
from app.schemas.api import AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    ctx: AuthContext = Depends(capability("view_audit_logs")), db: Session = Depends(get_db)
) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == ctx.organization_id)
            .order_by(AuditLog.created_at.desc())
            .limit(200)
        )
    )
