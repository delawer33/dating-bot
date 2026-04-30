from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict


@dataclass
class StrategyMetrics:
    requests: int = 0
    latency_ms_sum: float = 0.0
    db_hits: int = 0
    db_writes: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_writes: int = 0


class MetricsStore:
    def __init__(self) -> None:
        self._by_strategy: dict[str, StrategyMetrics] = {
            "lazy": StrategyMetrics(),
            "write-through": StrategyMetrics(),
            "write-back": StrategyMetrics(),
        }
        self._lock = asyncio.Lock()

    async def add_request(self, strategy: str, latency_ms: float) -> None:
        async with self._lock:
            metrics = self._by_strategy[strategy]
            metrics.requests += 1
            metrics.latency_ms_sum += latency_ms

    async def add_db_hit(self, strategy: str) -> None:
        async with self._lock:
            self._by_strategy[strategy].db_hits += 1

    async def add_db_write(self, strategy: str) -> None:
        async with self._lock:
            self._by_strategy[strategy].db_writes += 1

    async def add_cache_hit(self, strategy: str) -> None:
        async with self._lock:
            self._by_strategy[strategy].cache_hits += 1

    async def add_cache_miss(self, strategy: str) -> None:
        async with self._lock:
            self._by_strategy[strategy].cache_misses += 1

    async def add_cache_write(self, strategy: str) -> None:
        async with self._lock:
            self._by_strategy[strategy].cache_writes += 1

    async def reset(self, strategy: str) -> None:
        async with self._lock:
            self._by_strategy[strategy] = StrategyMetrics()

    async def snapshot(self, strategy: str) -> dict[str, float]:
        async with self._lock:
            metrics = self._by_strategy[strategy]
            result = asdict(metrics)

        requests = result["requests"]
        cache_total = result["cache_hits"] + result["cache_misses"]
        result["avg_latency_ms"] = (result["latency_ms_sum"] / requests) if requests else 0.0
        result["throughput_rps"] = 0.0
        result["cache_hit_rate"] = (result["cache_hits"] / cache_total) if cache_total else 0.0
        return result
