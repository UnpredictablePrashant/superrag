from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability
from app.db.session import get_db
from app.schemas.api import AIUsageSummaryOut
from app.services.usage import ai_usage_summary

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/ai-assistant", response_model=AIUsageSummaryOut)
def get_ai_assistant_usage(
    days: int = Query(default=30, ge=1, le=365),
    ctx: AuthContext = Depends(capability("view_audit_logs")),
    db: Session = Depends(get_db),
) -> dict:
    return ai_usage_summary(db, ctx.organization_id, days)
