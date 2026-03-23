# Сервисы

Логические сервисы для dating-бота. На старте они могут жить как пакеты в одном репозитории, а позже быть разделены на deployable units.

## Telegram Bot

- Long-polling или webhook к Telegram Bot API.
- Обрабатывает `/start`, сценарий регистрации.
- Вызывает Profile API как источник истины.

## Profile API (FastAPI)

- REST (или внутренний JSON) API: пользователи, профили, метаданные фото, preferences, endpoint `next`.
- Интегрирует результат ранжирования с **Redis prefetch queues**.
- Выдаёт presigned uploads для MinIO; сохраняет `s3_key` и порядок в PostgreSQL.
- Публикует события в RabbitMQ после успешных коммитов в БД.

## Ranking / scoring

- Pure functions (library): Level 1 (полнота профиля, фото, соответствие preferences), Level 2 (входы из `user_behavior_stats`), Level 3 (weighted combination + referral bonus).
- Читает/пишет `user_ratings` (и optional breakdown JSON). Вызывается из API и Celery workers.

## Interaction / event pipeline (RabbitMQ)

- Публикация **domain events** после likes, skips и matches, чтобы другие части системы могли реагировать без замедления request.
- Consumers синхронизируют **`user_behavior_stats`** (и связанные агрегаты) по этим событиям.
- Долгосрочная истина хранится в **PostgreSQL** (`profile_interactions`, `matches`)

## Worker (Celery)

- Обрабатывает background tasks через workers.
- Выполняет **scheduled** пересчёт **`user_ratings`** (основная ответственность).

## Media (MinIO)

- S3-compatible object storage для фото профилей.

## Observability

- Structured logging (JSON), correlation IDs от Bot → API → workers.
- Metrics: HTTP latency, queue depth, Celery task duration, Redis hit rate для prefetch.
- Health endpoints в Profile API; RabbitMQ management plugin
