"""Central logging: service name, optional request correlation, JSON or text to stderr."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str) -> contextvars.Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    _request_id.reset(token)


def sanitize_incoming_request_id(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s or len(s) > 128 or not _REQUEST_ID_RE.fullmatch(s):
        return None
    return s


class _ServiceContextFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service_name  # type: ignore[attr-defined]
        rid = get_request_id()
        record.request_id = rid if rid else "-"  # type: ignore[attr-defined]
        return True


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line; suitable for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": getattr(record, "service", ""),
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = getattr(record, "request_id", None)
        if rid and rid != "-":
            payload["request_id"] = rid
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(
    *,
    service: str,
    log_level: str = "INFO",
    json_logs: bool = False,
) -> None:
    """Configure the root logger once (safe to call again: replaces handlers)."""
    root = logging.getLogger()
    root.handlers.clear()

    numeric = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric, int):
        numeric = logging.INFO
    root.setLevel(numeric)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(numeric)
    handler.addFilter(_ServiceContextFilter(service))

    if json_logs:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt=(
                    "%(asctime)s %(levelname)s [%(service)s] [rid=%(request_id)s] "
                    "%(name)s: %(message)s"
                ),
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    root.addHandler(handler)

    # Quieter defaults for very chatty third-party loggers in production-ish setups
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aio_pika").setLevel(logging.INFO)
