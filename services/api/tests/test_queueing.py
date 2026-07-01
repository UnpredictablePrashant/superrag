from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.queueing import enqueue_pipeline_run


def test_pipeline_enqueue_uses_celery_when_kafka_disabled(monkeypatch) -> None:
    run_id = uuid4()
    calls: list[str] = []
    monkeypatch.setattr(settings, "kafka_enabled", False)
    monkeypatch.setattr("app.services.queueing._enqueue_pipeline_run_celery", lambda value: calls.append(str(value)))

    enqueue_pipeline_run(run_id)

    assert calls == [str(run_id)]


def test_pipeline_enqueue_publishes_to_kafka_when_enabled(monkeypatch) -> None:
    run_id = uuid4()
    published: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "kafka_enabled", True)
    monkeypatch.setattr(
        "app.services.queueing._publish_pipeline_run_event",
        lambda value, reason: published.append((str(value), reason)),
    )
    monkeypatch.setattr("app.services.queueing._enqueue_pipeline_run_celery", lambda _value: pytest.fail("unexpected fallback"))

    enqueue_pipeline_run(run_id, reason="created")

    assert published == [(str(run_id), "created")]


def test_pipeline_enqueue_falls_back_to_celery_when_kafka_publish_fails(monkeypatch) -> None:
    run_id = uuid4()
    calls: list[str] = []
    monkeypatch.setattr(settings, "kafka_enabled", True)
    monkeypatch.setattr(settings, "kafka_fallback_to_celery", True)

    def fail_publish(_value, reason):
        raise RuntimeError(f"publish failed: {reason}")

    monkeypatch.setattr("app.services.queueing._publish_pipeline_run_event", fail_publish)
    monkeypatch.setattr("app.services.queueing._enqueue_pipeline_run_celery", lambda value: calls.append(str(value)))

    enqueue_pipeline_run(run_id, reason="retry")

    assert calls == [str(run_id)]
