from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_organization
from app.db.session import get_db
from app.models.entities import Notification
from app.schemas.api import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    ctx: AuthContext = Depends(require_organization), db: Session = Depends(get_db)
) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(
                Notification.organization_id == ctx.organization_id,
                or_(Notification.user_id == ctx.user.id, Notification.user_id.is_(None)),
            )
            .order_by(Notification.created_at.desc())
            .limit(100)
        )
    )


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> Notification:
    notification = db.get(Notification, notification_id)
    if not notification or notification.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    notification.read_at = datetime.now(UTC)
    db.commit()
    db.refresh(notification)
    return notification
