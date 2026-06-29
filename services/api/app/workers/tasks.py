from __future__ import annotations

from uuid import UUID

from app.db.session import SessionLocal
from app.models.entities import TelegramIntegration
from app.services.pipeline import process_pipeline_run
from app.services.telegram import process_telegram_update
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def process_pipeline_run_task(self, pipeline_run_id: str) -> None:
    db = SessionLocal()
    try:
        process_pipeline_run(db, UUID(pipeline_run_id))
    finally:
        db.close()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def process_telegram_update_task(self, integration_id: str, update: dict) -> None:
    db = SessionLocal()
    try:
        integration = db.get(TelegramIntegration, UUID(integration_id))
        if not integration or integration.deleted_at is not None or not integration.is_enabled:
            return
        process_telegram_update(db, integration, update)
    finally:
        db.close()
