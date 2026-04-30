from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

import httpx


APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
RESULTS_PATH = Path(os.getenv("RESULTS_PATH", "/workspace/README.md"))
TOTAL_REQUESTS = 500

SCENARIOS = {
    "read-heavy": 0.8,
    "balanced": 0.5,
    "write-heavy": 0.2,
}

STRATEGIES = ["lazy", "write-through", "write-back"]


@dataclass
class RunResult:
    strategy: str
    scenario: str
    throughput_rps: float
    avg_latency_ms: float
    db_hits: int
    cache_hit_rate: float
    db_writes: int


def strategy_base_path(strategy: str) -> str:
    return {
        "lazy": "/lazy",
        "write-through": "/write-through",
        "write-back": "/write-back",
    }[strategy]


async def request_once(client: httpx.AsyncClient, strategy: str, read_ratio: float) -> None:
    item_id = random.randint(1, 100)
    if random.random() <= read_ratio:
        await client.get(f"{strategy_base_path(strategy)}/items/{item_id}")
        return

    payload = {"value": f"generated_value_{random.randint(1, 999999)}"}
    await client.post(f"{strategy_base_path(strategy)}/items/{item_id}", json=payload)


async def run_case(client: httpx.AsyncClient, strategy: str, scenario: str, read_ratio: float) -> RunResult:
    print(f"[RUN] strategy={strategy}, scenario={scenario}, read_ratio={read_ratio}")

    await client.post("/seed")
    await client.post(f"/metrics/{strategy}/reset")

    started_at = time.perf_counter()
    tasks = [request_once(client, strategy, read_ratio) for _ in range(TOTAL_REQUESTS)]
    await asyncio.gather(*tasks)
    elapsed_s = time.perf_counter() - started_at

    if strategy == "write-back":
        await asyncio.sleep(2.5)
        await client.post("/flush/write-back")

    metrics_response = await client.get(f"/metrics/{strategy}")
    metrics = metrics_response.json()

    throughput_rps = TOTAL_REQUESTS / elapsed_s if elapsed_s > 0 else 0.0

    result = RunResult(
        strategy=strategy,
        scenario=scenario,
        throughput_rps=throughput_rps,
        avg_latency_ms=float(metrics.get("avg_latency_ms", 0.0)),
        db_hits=int(metrics.get("db_hits", 0)),
        cache_hit_rate=float(metrics.get("cache_hit_rate", 0.0)),
        db_writes=int(metrics.get("db_writes", 0)),
    )

    print(
        "[DONE] "
        f"strategy={strategy}, scenario={scenario}, "
        f"throughput={result.throughput_rps:.2f} req/s, "
        f"avg_latency={result.avg_latency_ms:.2f} ms, "
        f"db_hits={result.db_hits}, cache_hit_rate={result.cache_hit_rate:.2%}, db_writes={result.db_writes}"
    )
    return result


def choose_best(results: list[RunResult], scenario: str, by: str, higher_is_better: bool) -> str:
    scoped = [row for row in results if row.scenario == scenario]
    if not scoped:
        return "нет данных"
    if higher_is_better:
        best = max(scoped, key=lambda row: getattr(row, by))
    else:
        best = min(scoped, key=lambda row: getattr(row, by))
    return best.strategy


def build_report(results: list[RunResult]) -> str:
    lines: list[str] = []
    lines.append("# Cache Comparison Practice — Report")
    lines.append("")
    lines.append("## Описание теста")
    lines.append("")
    lines.append("- Система: FastAPI + Redis + PostgreSQL + самописный load-generator.")
    lines.append("- Всего стратегий: 3 (Lazy Loading/Cache-Aside, Write-Through, Write-Back).")
    lines.append("- Для каждой стратегии проведено 3 прогона: read-heavy (80/20), balanced (50/50), write-heavy (20/80).")
    lines.append(f"- На каждый прогон отправлено {TOTAL_REQUESTS} запросов по id 1..100.")
    lines.append("")
    lines.append("## Таблица результатов")
    lines.append("")
    lines.append("| Стратегия | Сценарий | Throughput (req/s) | Средняя задержка (ms) | Обращения в БД (чтение) | Hit rate кеша | DB writes |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")

    sorted_rows = sorted(results, key=lambda row: (row.scenario, row.strategy))
    for row in sorted_rows:
        lines.append(
            "| "
            f"{row.strategy} | {row.scenario} | {row.throughput_rps:.2f} | {row.avg_latency_ms:.2f} | "
            f"{row.db_hits} | {row.cache_hit_rate:.2%} | {row.db_writes} |"
        )

    lines.append("")
    lines.append("## Выводы")
    lines.append("")

    best_read = choose_best(results, "read-heavy", "throughput_rps", True)
    best_write = choose_best(results, "write-heavy", "throughput_rps", True)
    best_balanced = choose_best(results, "balanced", "throughput_rps", True)

    lines.append(f"- Для чтения (read-heavy) лучшая стратегия по throughput: `{best_read}`.")
    lines.append(f"- Для записи (write-heavy) лучшая стратегия по throughput: `{best_write}`.")
    lines.append(f"- Для смешанной нагрузки (balanced) лучшая стратегия по throughput: `{best_balanced}`.")

    write_back_rows = [row for row in results if row.strategy == "write-back"]
    if write_back_rows:
        max_db_writes = max(row.db_writes for row in write_back_rows)
        min_db_writes = min(row.db_writes for row in write_back_rows)
        lines.append(
            "- Для Write-Back видно отложенную запись: "
            f"в момент нагрузки DB writes может быть ниже, а затем догоняет после flush (диапазон в тестах: {min_db_writes}..{max_db_writes})."
        )

    lines.append("")
    lines.append("## Логи прогонов")
    lines.append("")
    lines.append("Ниже фрагменты консольных логов (выполнено через `docker compose run --rm load-generator`):")
    lines.append("")
    lines.append("```text")
    for row in sorted_rows:
        lines.append(
            "[DONE] "
            f"strategy={row.strategy}, scenario={row.scenario}, throughput={row.throughput_rps:.2f} req/s, "
            f"avg_latency={row.avg_latency_ms:.2f} ms, db_hits={row.db_hits}, cache_hit_rate={row.cache_hit_rate:.2%}, db_writes={row.db_writes}"
        )
    lines.append("```")

    return "\n".join(lines) + "\n"


async def main() -> None:
    results: list[RunResult] = []
    async with httpx.AsyncClient(base_url=APP_BASE_URL, timeout=30.0) as client:
        for strategy in STRATEGIES:
            for scenario, read_ratio in SCENARIOS.items():
                result = await run_case(client, strategy=strategy, scenario=scenario, read_ratio=read_ratio)
                results.append(result)

    report = build_report(results)
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(f"[REPORT] saved to {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
