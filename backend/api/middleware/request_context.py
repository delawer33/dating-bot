"""Request correlation id, access log line, and logging for unexpected errors."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from shared.logging_setup import reset_request_id, sanitize_incoming_request_id, set_request_id

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Set ``X-Request-ID`` context, log one access line, echo id on the response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        raw = request.headers.get("x-request-id")
        rid = sanitize_incoming_request_id(raw) or str(uuid.uuid4())
        token = set_request_id(rid)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except (HTTPException, RequestValidationError):
                raise
            except Exception:
                logger.exception(
                    "unhandled_exception method=%s path=%s",
                    request.method,
                    request.url.path,
                )
                raise

            duration_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Request-ID"] = rid
            if request.url.path not in ("/health", "/metrics"):
                logger.info(
                    "http_request request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f",
                    rid,
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                )
            return response
        finally:
            reset_request_id(token)
