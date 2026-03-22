# Services

Logical services for the dating bot. They can live in one repository as packages initially and be split into deployable units later.

## Telegram Bot

- Long-polling or webhook against the Telegram Bot API.
- Handles `/start`, registration wizard, discovery UX (show profile card, like / skip buttons).
- Calls the Profile API for authoritative state; **does not** publish to RabbitMQ — the API emits events after it persists actions.
- Sends users HTTPS URLs for photos (MinIO public or signed URLs as designed in Stage 3).

## Profile API (FastAPI)

- REST (or internal JSON) API: users, profiles, photos metadata, preferences, discovery `next` endpoint.
- Integrates ranking output with **Redis prefetch queues** (see [architecture.md](./architecture.md)).
- Issues presigned uploads for MinIO; persists `s3_key` and ordering in PostgreSQL.
- Publishes interaction-related events to RabbitMQ after successful DB commits (or via outbox—implementation choice in Stage 3).

## Ranking / scoring

- Pure functions (library): Level 1 (profile completeness, photos, preference fit), Level 2 (inputs from `user_behavior_stats`), Level 3 (weighted combination + referral bonus).
- Reads/writes `user_ratings` (and optional breakdown JSON). Invoked from API and Celery workers.

## Interaction / event pipeline (RabbitMQ)

- Publishes **domain events** after likes, skips, and matches so other parts of the system can react without slowing the request.
- Consumers keep **`user_behavior_stats`** (and related aggregates) in sync with those events.
- Long-term truth stays in **PostgreSQL** (`profile_interactions`, `matches`); RabbitMQ is for delivery, not the audit log.

## Worker (Celery)

- **Scheduled** recomputation of **`user_ratings`** (main responsibility).
- Optional: Redis discovery maintenance, cleanup, other batch work.

## Media (MinIO)

- S3-compatible object storage for profile images.
- API generates presigned PUT/POST; clients upload; API stores metadata in `profile_photos`.

## Observability

- Structured logging (JSON), correlation IDs from Bot → API → workers.
- Metrics: HTTP latency, queue depth, Celery task duration, Redis hit rate for prefetch.
- Health endpoints on Profile API; RabbitMQ management plugin or Prometheus plugin in non-dev environments.

Russian: [docs/ru/services.md](./ru/services.md).
