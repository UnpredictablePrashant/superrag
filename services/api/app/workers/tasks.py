from __future__ import annotations

from uuid import UUID

from app.db.session import SessionLocal
from app.models.entities import TelegramIntegration
from app.services.connectors import sync_connector_connection
from app.services.pipeline import process_pipeline_run
from app.services.relationship_intelligence import process_relationship_scan_run
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


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def process_connector_sync_task(
    self,
    connection_id: str,
    requested_by_user_id: str,
    options: dict,
    run_id: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        sync_connector_connection(
            db,
            connection_id=UUID(connection_id),
            requested_by_user_id=UUID(requested_by_user_id),
            options=options,
            run_id=UUID(run_id) if run_id else None,
        )
    finally:
        db.close()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def process_relationship_scan_task(self, scan_run_id: str) -> None:
    db = SessionLocal()
    try:
        process_relationship_scan_run(db, UUID(scan_run_id))
    finally:
        db.close()
