import asyncio
import enum
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

class ApiUnavailableError(Exception):
    """Raised when the API cannot be reached after retries or the circuit is open."""


_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)

_RETRY_ATTEMPTS = 3
_BASE_DELAY = 0.5
_MAX_DELAY = 8.0
_JITTER = 0.5


async def retry_with_backoff(coro_fn: Callable[[], Awaitable[T]]) -> T:
    last_exc: Exception | None = None

    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return await coro_fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise
            last_exc = exc
            logger.warning("API 5xx on attempt %d/%d: %s", attempt + 1, _RETRY_ATTEMPTS, exc)
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            logger.warning(
                "API network error on attempt %d/%d: %s: %s",
                attempt + 1,
                _RETRY_ATTEMPTS,
                type(exc).__name__,
                exc,
            )

        if attempt < _RETRY_ATTEMPTS - 1:
            delay = min(_BASE_DELAY * (2 ** attempt), _MAX_DELAY) + random.uniform(0, _JITTER)
            logger.debug("Retrying in %.2fs…", delay)
            await asyncio.sleep(delay)

    raise ApiUnavailableError(f"API unavailable after {_RETRY_ATTEMPTS} attempts") from last_exc


class _State(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Three-state circuit breaker (CLOSED → OPEN → HALF_OPEN → CLOSED).

    CLOSED   : normal operation; failures increment counter.
    OPEN     : rejects calls immediately; re-enters HALF_OPEN after open_timeout.
    HALF_OPEN: lets one probe through; success → CLOSED, failure → OPEN.
    """

    def __init__(self, failure_threshold: int = 5, open_timeout: float = 30.0) -> None:
        self._threshold = failure_threshold
        self._open_timeout = open_timeout
        self._state = _State.CLOSED
        self._failures = 0
        self._opened_at: float = 0.0

    async def execute(self, coro_fn: Callable[[], Awaitable[T]]) -> T:
        if self._state == _State.OPEN:
            if time.monotonic() - self._opened_at >= self._open_timeout:
                self._state = _State.HALF_OPEN
                logger.info("Circuit breaker → HALF_OPEN (probing API)")
            else:
                raise ApiUnavailableError("Circuit breaker is OPEN — API is unavailable")

        try:
            result = await coro_fn()
        except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
            is_client_error = (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code < 500
            )
            if not is_client_error:
                self._record_failure()
            raise

        self._record_success()
        return result

    def _record_failure(self) -> None:
        self._failures += 1
        if self._state == _State.HALF_OPEN or self._failures >= self._threshold:
            self._state = _State.OPEN
            self._opened_at = time.monotonic()
            self._failures = 0
            logger.error(
                "Circuit breaker → OPEN (will retry after %.0fs)", self._open_timeout
            )

    def _record_success(self) -> None:
        if self._state == _State.HALF_OPEN:
            logger.info("Circuit breaker → CLOSED (API recovered)")
        self._state = _State.CLOSED
        self._failures = 0
