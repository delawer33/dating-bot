"""Celery application — broker is RabbitMQ (same as aio-pika)."""

from __future__ import annotations

import os

from celery import Celery
from celery.signals import beat_init, worker_init

from shared.config import SharedConfig
from shared.logging_setup import configure_logging

_cfg = SharedConfig()


@worker_init.connect
def _configure_celery_worker_logging(**_kwargs: object) -> None:
    cfg = SharedConfig()
    configure_logging(
        service="celery-worker",
        log_level=cfg.log_level,
        json_logs=cfg.effective_log_json,
    )


@beat_init.connect
def _configure_celery_beat_logging(**_kwargs: object) -> None:
    cfg = SharedConfig()
    configure_logging(
        service="celery-beat",
        log_level=cfg.log_level,
        json_logs=cfg.effective_log_json,
    )
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
