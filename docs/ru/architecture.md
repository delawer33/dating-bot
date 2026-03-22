# Архитектура

Сквозное устройство dating-бота: клиент Telegram, сервис профилей на FastAPI, PostgreSQL, prefetch в Redis, RabbitMQ (события и фоновые задачи), MinIO для медиа, Celery для периодического обновления рейтингов.

## Диаграмма верхнего уровня

```mermaid
flowchart LR
  subgraph clients [Клиенты]
    TG[Telegram]
  end
  subgraph app [Приложение]
    Bot[Telegram_Bot]
    API[Profile_API_FastAPI]
    Rank[Ranking_logic]
  end
  subgraph data [Data_plane]
    PG[(PostgreSQL)]
    RD[(Redis)]
    S3[(MinIO_S3)]
  end
  subgraph async_plane [Async_plane]
    MQ[RabbitMQ]
    Cel[Celery_workers]
  end
  TG <--> Bot
  Bot --> API
  API --> Rank
  API --> PG
  API --> RD
  API --> S3
  API --> MQ
  MQ --> Cel
  Cel --> PG
  Cel --> RD
  Rank --> PG
```

## Маршрутизация RabbitMQ (проект)

- **Producers:** только **Profile API** — бот вызывает API; события публикуются после успешного сохранения в БД (один путь, без дублирующих publish).
- **Exchange:** `dating.events` — тип **topic** (или **headers**, если нужны только явные routing keys).
- **Routing keys:** `profile.liked`, `profile.skipped`, `match.created` (каталог событий ниже).
- **Queues:**
  - `behavior.aggregate` — **consumer** обновляет `user_behavior_stats` (и при необходимости запускает пересчёт рейтинга).
- **Durability:** durable exchange и queues; **persistent** messages для событий взаимодействий.
- **Failure handling:** DLQ на queue (например `behavior.aggregate.dlq`) после лимита повторов; poison messages разбираются вручную.

```mermaid
flowchart LR
  subgraph producers [Producers]
    API[Profile_API]
  end
  subgraph rmq [RabbitMQ]
    EX["dating.events (topic)"]
    Q1[behavior.aggregate]
    Q2[behavior.aggregate.dlq]
  end
  subgraph consumers [Consumers]
    C1[Stats_consumer]
  end
  API --> EX
  EX --> Q1
  Q1 --> C1
  Q1 -.->|failed| Q2
```

## Discovery и prefetch в Redis

API забирает следующий id через **`LPOP`** из Redis **LIST**; если список пуст или ключ истёк по TTL, выполняется ранжирование следующего кандидата, в очередь **`RPUSH`** около 10 id, пользователю отдаётся первый.

```mermaid
sequenceDiagram
  participant U as User
  participant Bot as Telegram_Bot
  participant API as Profile_API
  participant R as Redis
  participant Rank as Ranking
  U->>Bot: Open_session_or_next
  Bot->>API: GET_next_profile
  API->>R: LPOP_prefetch_list
  alt queue_empty_or_expired
    API->>Rank: full_pipeline_top_candidate
    Rank->>API: profile_id
    API->>R: RPUSH_batch_next_10
  end
  API-->>Bot: profile_payload
  Bot-->>U: Show_card
```

### Соглашения по ключам Redis

| Key | Role |
|-----|------|
| `discovery:queue:{viewer_user_id}` | FIFO list следующих `profile_id`. TTL ~15–30 мин; **DEL при смене настроек**; дозаполнять при len ≤ ~2. |
| `session:{viewer_user_id}` | Краткоживущий FSM / черновики (не истина в БД). По возможности кнопки через `callback_data`. TTL + touch; DEL по завершении или отмене. Один writer: Bot *или* API. |

Discovery — очередь карточек; session — шаг сценария в чате. Смена настроек → инвалидировать только discovery.

## Каталог событий (payloads RabbitMQ)

**Envelope** (JSON, UTF-8):

```json
{
  "event_id": "uuid",
  "type": "profile.liked",
  "occurred_at": "2025-03-22T12:00:00Z",
  "schema_version": 1,
  "payload": {}
}
```

| type | payload (минимум) |
|------|-------------------|
| `profile.liked` | `actor_user_id`, `target_user_id`, `interaction_id` |
| `profile.skipped` | то же |
| `match.created` | `match_id`, `user_a_id`, `user_b_id` |


## Фоновые задачи (Celery)

Celery **по расписанию** (Celery Beat) пересчитывает **user ratings** и пишет результат в БД, чтобы свайпы и вызовы API оставались лёгкими. Сюда же можно вынести прочие задачи (например обслуживание cache).


## Observability

- FastAPI: request metrics, доля 4xx/5xx.
- RabbitMQ: queue depth, **consumer** utilization, DLQ rate.
- Celery: task success/failure, latency.
- Redis: memory, evictions, hit ratio по ключам discovery.

## Связанные документы

- [services.md](./services.md) — зоны ответственности сервисов.
- [database-schema.md](./database-schema.md) — таблицы и индексы PostgreSQL.
