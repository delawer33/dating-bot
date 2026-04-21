# Dating bot

Dating-бот в Telegram с ранжированной выдачей, PostgreSQL, Redis prefetch queues, RabbitMQ (events и background tasks), MinIO для фото и Celery воркеров

## Документация

| Документ                                                 | Описание                    |
| -------------------------------------------------------- | --------------------------- |
| [docs/ru/services.md](docs/ru/services.md)               | Русская версия: сервисы     |
| [docs/ru/architecture.md](docs/ru/architecture.md)       | Русская версия: архитектура |
| [docs/ru/database-schema.md](docs/ru/database-schema.md) | Русская версия: схема БД    |

## Roadmap

1. **Stage 1 — Планирование и дизайн** (текущий): сервисы, архитектура, схема БД, базовая подготовка репозитория.
2. **Stage 2 — Core functionality**: Telegram-бот, регистрация через `/start`, база FastAPI.
3. **Stage 3 — Профили и ранжирование**: CRUD, ранжирование, Redis prefetch, интеграция RabbitMQ.
4. **Stage 4 — Hardening**: расписания Celery, тюнинг БД, тесты, производительность, deploy/demo.

## Tech stack

- Python, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async)
- PostgreSQL, Redis, RabbitMQ, MinIO (S3-compatible), Celery

## Running Stage 2 (dev)

```bash
# 1. Copy and edit env
cp backend/.env.example backend/.env
# Fill in: BOT_TOKEN, BOT_SECRET, API_SECRET (must match)

# 2. Start infrastructure + API + bot
docker compose up --build

# Migrations run automatically via the `migrate` service.
# API docs: http://localhost:8000/docs
```

### Switching to webhook mode (prod)

In `backend/.env`:

```
BOT_TRANSPORT=webhook
WEBHOOK_URL=https://bot.yourdomain.com/webhook
WEBHOOK_SECRET_TOKEN=<random-secret>
APP_ENV=prod
```

### Running without Docker (local dev)

```bash
cd backend
pip install -r requirements-dev.txt

# Start Postgres + Redis via docker compose infra only:
docker compose up postgres redis -d

# Run migrations
alembic upgrade head

# API (terminal 1)
uvicorn api.main:app --reload

# Bot (terminal 2)
python -m bot.main
```
