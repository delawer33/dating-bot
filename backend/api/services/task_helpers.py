"""Fire-and-forget Celery jobs from the API (best-effort)."""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def schedule_rating_recompute(user_id: uuid.UUID) -> None:
    try:
        from workers.celery_app import celery_app

        celery_app.send_task("rating.recompute_user", args=[str(user_id)])
    except Exception:
        logger.exception("Could not enqueue rating.recompute_user for %s", user_id)
