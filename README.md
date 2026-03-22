# Dating bot

Telegram-based dating bot with ranked discovery, PostgreSQL, Redis prefetch queues, RabbitMQ (events and background tasks), MinIO for photos, Celery for scheduled rating updates.

## Docs

| Document | Description |
|----------|-------------|
| [docs/services.md](docs/services.md) | Service boundaries and responsibilities |
| [docs/architecture.md](docs/architecture.md) | System diagram, RabbitMQ routing, Redis keys, event catalog |
| [docs/database-schema.md](docs/database-schema.md) | PostgreSQL tables, indexes, ER overview |


## Roadmap

1. **Stage 1 — Planning and design** (current): services, architecture, DB schema, repo hygiene.
2. **Stage 2 — Core functionality**: Telegram bot, `/start` registration, FastAPI foundation.
3. **Stage 3 — Profiles and ranking**: CRUD, ranking (levels 1–3 minimal slice), Redis prefetch, RabbitMQ integration.
4. **Stage 4 — Hardening**: Celery schedules, DB tuning, tests, performance, deploy/demo.


## Tech stack

- Python, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async)
- PostgreSQL, Redis, RabbitMQ, MinIO (S3-compatible), Celery

