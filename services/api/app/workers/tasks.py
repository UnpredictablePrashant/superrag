from __future__ import annotations

from uuid import UUID

from app.db.session import SessionLocal
from app.services.pipeline import process_pipeline_run
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def process_pipeline_run_task(self, pipeline_run_id: str) -> None:
    db = SessionLocal()
    try:
        process_pipeline_run(db, UUID(pipeline_run_id))
    finally:
        db.close()
