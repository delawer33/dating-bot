import asyncio
import time


class TokenBucketRateLimiter:
    """
    Async token-bucket rate limiter.

    Refills at `rate` tokens per second. Each call to `acquire()` waits
    until a token is available, then consumes it. This provides smooth,
    accurate pacing even at high rates — unlike sleep-based approaches
    which accumulate drift.
    """

    def __init__(self, rate: float) -> None:
        self._rate = rate
        self._tokens: float = rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            wait_time = (1.0 - self._tokens) / self._rate
            self._tokens = 0.0

        await asyncio.sleep(wait_time)
