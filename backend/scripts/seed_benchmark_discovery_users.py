#!/usr/bin/env python3
"""Insert registered users for discovery JMeter runs (idempotent on telegram_id).

Run from the backend tree with DATABASE_URL set, for example:

  cd backend
  DATABASE_URL=postgresql+asyncpg://dating:dating@localhost:5432/dating \\
    python scripts/seed_benchmark_discovery_users.py

Or via Docker Compose (API service has /app as cwd and backend on PYTHONPATH):

  docker compose exec api python scripts/seed_benchmark_discovery_users.py

  Optional: write viewers CSV on the host (run from backend/ with DATABASE_URL):

  python scripts/seed_benchmark_discovery_users.py --count 400 \\
    --write-viewers-csv ../benchmarks/jmeter/viewers.csv
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Scripts run with cwd /app in Docker; local runs use backend/ as cwd.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from shared.db.models import User  # noqa: E402
from tests.factories.users import insert_user_with_profile  # noqa: E402


async def _exists(session: AsyncSession, telegram_id: int) -> bool:
    r = await session.execute(select(User.id).where(User.telegram_id == telegram_id))
    return r.scalar_one_or_none() is not None


async def _run(start: int, count: int) -> tuple[int, int]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required.")

    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    skipped = 0
    try:
        async with factory() as session:
            for i in range(count):
                tid = start + i
                if await _exists(session, tid):
                    skipped += 1
                    continue
                gender = "male" if i % 2 == 0 else "female"
                await insert_user_with_profile(
                    session,
                    telegram_id=tid,
                    display_name=f"Bench {tid}",
                    gender=gender,
                    gender_preferences=["male", "female"],
                    max_distance_km=None,
                    combined_rating=float(i % 20),
                    registration_completed=True,
                )
                created += 1
    finally:
        await engine.dispose()
    return created, skipped


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--start",
        type=int,
        default=9_100_000_000_001,
        help="First telegram_id (default matches benchmarks/jmeter/viewers.csv).",
    )
    p.add_argument(
        "--count",
        type=int,
        default=400,
        help="How many consecutive ids to ensure (default sized for load tests).",
    )
    p.add_argument(
        "--write-viewers-csv",
        type=Path,
        default=None,
        help="Write telegram_id header + one row per id in [start, start+count) (host path; run from repo root).",
    )
    args = p.parse_args()
    created, skipped = asyncio.run(_run(args.start, args.count))
    print(f"seed_benchmark_discovery_users: created={created} skipped={skipped}")
    if args.write_viewers_csv is not None:
        path = args.write_viewers_csv.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["telegram_id"] + [str(args.start + i) for i in range(args.count)]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {path} ({args.count} ids)")


if __name__ == "__main__":
    main()
