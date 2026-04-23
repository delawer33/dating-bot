"""Celery application — broker is RabbitMQ (same as aio-pika)."""

from __future__ import annotations

import os

from celery import Celery

from shared.config import SharedConfig

_cfg = SharedConfig()
_broker = os.environ.get("CELERY_BROKER_URL", _cfg.rabbitmq_url)
_backend = os.environ.get("CELERY_RESULT_BACKEND", _cfg.redis_url)

celery_app = Celery(
    "dating",
    broker=_broker,
    backend=_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "recompute-all-ratings": {
        "task": "rating.recompute_all",
        "schedule": 120.0,
    },
}

import workers.rating_tasks  # noqa: E402 — register Celery tasks
