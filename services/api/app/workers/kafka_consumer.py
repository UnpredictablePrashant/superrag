from __future__ import annotations

import json
import signal
import time
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import PipelineRun, PipelineStage
from app.services.pipeline import process_pipeline_run

_running = True


def main() -> None:
    if not settings.kafka_enabled:
        raise RuntimeError("Kafka pipeline worker requires KAFKA_ENABLED=true.")
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    _recover_queued_pipeline_runs()
    consumer = _consumer()
    try:
        while _running:
            _recover_queued_pipeline_runs(limit=5)
            records = consumer.poll(timeout_ms=1000, max_records=10)
            for partition_records in records.values():
                for record in partition_records:
                    _handle_record(record.value)
                    consumer.commit()
    finally:
        consumer.close()


def _consumer():
    from kafka import KafkaConsumer

    return KafkaConsumer(
        settings.kafka_pipeline_topic,
        bootstrap_servers=_bootstrap_servers(),
        group_id=settings.kafka_pipeline_consumer_group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        consumer_timeout_ms=1000,
    )


def _handle_record(value: dict) -> None:
    if value.get("event_type") != "pipeline_run_queued":
        return
    pipeline_run_id = UUID(str(value["pipeline_run_id"]))
    db = SessionLocal()
    try:
        process_pipeline_run(db, pipeline_run_id)
    finally:
        db.close()


def _recover_queued_pipeline_runs(limit: int = 20) -> None:
    db = SessionLocal()
    try:
        run_ids = list(
            db.scalars(
                select(PipelineRun.id)
                .where(PipelineRun.current_stage == PipelineStage.QUEUED)
                .order_by(PipelineRun.created_at)
                .limit(limit)
            )
        )
    finally:
        db.close()
    for run_id in run_ids:
        db = SessionLocal()
        try:
            process_pipeline_run(db, run_id)
        finally:
            db.close()
        if not _running:
            break
        time.sleep(0.05)


def _bootstrap_servers() -> list[str]:
    return [server.strip() for server in settings.kafka_bootstrap_servers.split(",") if server.strip()]


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


if __name__ == "__main__":
    main()
