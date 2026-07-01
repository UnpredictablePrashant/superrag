from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from app.core.config import settings


def enqueue_pipeline_run(pipeline_run_id: UUID | str, *, reason: str = "queued") -> None:
    if settings.kafka_enabled:
        try:
            _publish_pipeline_run_event(pipeline_run_id, reason=reason)
            return
        except Exception:
            if not settings.kafka_fallback_to_celery:
                raise
    _enqueue_pipeline_run_celery(pipeline_run_id)


def _publish_pipeline_run_event(pipeline_run_id: UUID | str, *, reason: str) -> None:
    from kafka import KafkaProducer

    producer = KafkaProducer(
        bootstrap_servers=_bootstrap_servers(),
        acks="all",
        retries=5,
        linger_ms=10,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        key_serializer=lambda value: str(value).encode("utf-8"),
    )
    try:
        future = producer.send(
            settings.kafka_pipeline_topic,
            key=str(pipeline_run_id),
            value={
                "event_type": "pipeline_run_queued",
                "pipeline_run_id": str(pipeline_run_id),
                "reason": reason,
                "queued_at": datetime.now(UTC).isoformat(),
            },
        )
        future.get(timeout=15)
        producer.flush(timeout=10)
    finally:
        producer.close(timeout=5)


def _enqueue_pipeline_run_celery(pipeline_run_id: UUID | str) -> None:
    from app.workers.tasks import process_pipeline_run_task

    process_pipeline_run_task.delay(str(pipeline_run_id))


def _bootstrap_servers() -> list[str]:
    return [server.strip() for server in settings.kafka_bootstrap_servers.split(",") if server.strip()]
