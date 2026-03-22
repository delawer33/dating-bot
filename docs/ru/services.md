# Сервисы

Логические сервисы dating-бота. Изначально могут жить в одном репозитории пакетами, позже вынести в отдельные deployable units.

## Telegram Bot

- Long-polling или webhook к Telegram Bot API.
- `/start`, сценарий регистрации, discovery UX (карточка профиля, кнопки like / skip).
- Вызывает Profile API за истинным состоянием; **не** публикует в RabbitMQ — события шлёт API после сохранения действий.
- Отдаёт пользователям HTTPS-ссылки на фото (публичные или signed URLs MinIO — этап 3).

## Profile API (FastAPI)

- REST (или внутренний JSON): пользователи, профили, метаданные фото, настройки, эндпоинт discovery `next`.
- Сводит ранжирование с **Redis prefetch queues** (см. [architecture.md](./architecture.md)).
- Выдаёт presigned uploads в MinIO; хранит `s3_key` и порядок в PostgreSQL.
- После успешного commit в БД публикует события взаимодействий в RabbitMQ (или через outbox — решение на этапе 3).

## Ranking / scoring

- Чистые функции (библиотека): уровень 1 (полнота профиля, фото, соответствие настройкам), уровень 2 (входы из `user_behavior_stats`), уровень 3 (weighted combination + referral bonus).
- Читает/пишет `user_ratings` (и опционально breakdown JSON). Вызывается из API и Celery workers.

## Interaction / event pipeline (RabbitMQ)

- Публикует **domain events** после лайков, скипов и матчей, чтобы остальная система реагировала без замедления request.
- **Consumers** поддерживают актуальность **`user_behavior_stats`** (и связанных агрегатов) по этим событиям.
- Долгосрочная истина — в **PostgreSQL** (`profile_interactions`, `matches`); RabbitMQ для delivery, не audit log.

## Worker (Celery)

- **Scheduled** пересчёт **`user_ratings`** (основная задача).
- По желанию: обслуживание discovery в Redis, cleanup, прочий batch.

## Media (MinIO)

- S3-compatible object storage для фото профилей.
- API генерирует presigned PUT/POST; clients upload; метаданные — в `profile_photos`.

## Observability

- Structured logging (JSON), correlation IDs от Bot → API → workers.
- Metrics: HTTP latency, queue depth, длительность Celery task, Redis hit rate для prefetch.
- Health endpoints на Profile API; в non-dev — RabbitMQ management plugin или Prometheus plugin.

English: [services.md](../services.md).
