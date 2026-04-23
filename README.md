# Дейтинг-бот в Telegram

Telegram-бот для знакомств

## Возможности

- **Регистрация** по шагам: геолокация/город, фото (лимиты min/max), параметры поиска (возраст, пол, макс. дистанция), опционально био и интересы, завершение `POST /registration/complete`.
- **Лента знакомств (discovery):** `like` / `skip` / следующая анкета; фильтры зрителя; очередь кандидатов в Redis; карточка профиля из БД.
- **Матчи** и учёт взаимодействий; события в RabbitMQ (`dating.events`) для воркера поведения и пересчёта рейтинга.
- **Рейтинг пользователей** (`user_ratings.combined_score`): первичный скор из полноты профиля, поведенческий из лайков/скипов/матчей, бонус за рефералов; пересчёт через Celery и при ключевых событиях.
- **Профиль и настройки в боте:** меню, мой профиль, параметры поиска, добавление/удаление фото, **порядок фото** (inline: стабильные номера фото и строка «Сейчас в ленте» при перестановке).
- **Рефералы:** событие при первом успешном завершении регистрации приглашённого; влияние на рейтинг реферера.
- **Транспорт бота:** polling (dev) или webhook (prod), единая точка в `bot/transport/`.

Подробнее по сервисам и схеме БД: [docs/ru/services.md](docs/ru/services.md), [docs/ru/architecture.md](docs/ru/architecture.md), [docs/ru/database-schema.md](docs/ru/database-schema.md).

---

## Алгоритм рекомендаций и рейтинга

### Рекомендации и рейтинг (кратко)

**Лента:** SQL-фильтры зрителя → сортировка по **`combined_score`** → при необходимости **Haversine** + **`max_distance_km`** → первые **10** UUID → Redis `discovery:queue:{viewer_id}` → по одному ID карточка из БД. Redis хранит **только ID**, не JSON анкет.

**Код:** `discovery_service.py` · `rating_algorithms.py` · `rating_service.py`

#### Соответствие `rating-algos.md` → код

| Уровень (`rating-algos.md`) | В коде |
|----------------------------|--------|
| **Level 1: Primary Rating** (анкета, полнота, фото, предпочтения) | Один числовой вход: **`completeness_score` / 100** + бонус **+0.02**, если задан **`max_distance_km`** (потолок 1). Отдельные поля анкеты в формулу **не** входят — они уже могут влиять на `completeness_score` при расчёте профиля. |
| **Level 2: Behavioral rating** (лайки, ratio, matches, диалоги, время суток) | Лайки **L**, скипы **S**, матчи **M** из `user_behavior_stats`. **Нет:** диалогов после матча; **histogram по времени** пишется воркером, в скор **не** входит. |
| **Level 3: Combined Rating** + **referral** | Взвешенная сумма **primary** + **behavioral** + **`referral_bonus`**, затем **clamp** в отрезок **0…1**. |

#### Формулы (`rating_algorithms.py`, `v1.0.0`)

Обозначения: **C** — `completeness_score` (0…100), **L, S, M** — лайки / скипы / матчи «на пользователя», **n** — число успешных рефералов, **eps** = `1e-9` (как в коде).

`clamp(x, lo, hi)` = min(hi, max(lo, x)).

##### Level 1 — `primary`

```
base   = clamp(C / 100, 0, 1)
primary = min(1, base + 0.02)   если задан max_distance_km в preferences
primary = base                  иначе
```

##### Level 2 — `behavioral`

Cold start (нет строки `user_behavior_stats`):

```
behavioral = 0.32
```

Иначе (`log1p` = натуральный log(1 + x), как в Python):

```
like_ratio   = L / (L + S + eps)
engagement   = clamp( log1p(L + 2*M) / log1p(80), 0, 1 )
match_signal = clamp( log1p(M)     / log1p(25), 0, 1 )

behavioral = clamp( 0.45*like_ratio + 0.35*engagement + 0.20*match_signal, 0, 1 )
```

##### Referral — `referral_bonus`

**Кому:** пользователю, **чей реферальный код** ввёл приглашённый (реферер). **Когда:** после того как приглашённый (рефери) **успешно завершает регистрацию** (`POST /registration/complete`), в БД появляется строка `referral_events` (одна на рефери: `referrer_id` → реферер, `referee_id` → рефери), и для реферера пересчитывается рейтинг — в формулу входит число таких строк **n** за всё время.

```
referral_bonus = min(0.12, 0.03 * n)
```

##### Level 3 — `combined` → `user_ratings.combined_score`

Константы: **`WEIGHT_PRIMARY = 0.42`**, **`WEIGHT_BEHAVIORAL = 0.43`**.

```
raw      = 0.42 * primary + 0.43 * behavioral + referral_bonus
combined = clamp(raw, 0, 1)
```

#### Обновление рейтинга

- **Поведение и реферал:** лайк / скип / матч → **RabbitMQ** → `behavior_consumer` → счётчики → **Celery** `rating.recompute_user` → upsert **`user_ratings`**.
- **Завершение регистрации:** сразу после commit в `complete_registration` синхронно пересчитываются **`user_ratings`** для **рефери** и (если сработал новый реферал) для **реферера**; параллельно по-прежнему ставится задача в Celery для согласованности.

#### Не в скоре

**Level 2** из спеки: *dialog after match*, *time-of-day в формуле*.

---

## Тестирование

Тесты лежат в **`backend/tests/`**, запускаются **pytest** из каталога `backend`.

| Каталог / файл | Назначение |
|----------------|------------|
| `tests/unit/` | Изолированные unit-тесты: формулы рейтинга (`test_rating_algorithms.py`), геодистанция discovery (`test_discovery_geo.py`), схемы discovery (`test_discovery_schemas.py`), регистрация (`test_registration.py`), геокодинг (`test_geocoding.py`), форматирование меню настроек (`test_menu_prefs_format.py`), ошибки API для бота (`test_api_errors.py`), Telegram file service, notify, транспорт бота (`test_transport.py`). |
| `tests/integration/` | Сценарии через **TestClient** FastAPI с подменой сессии БД, Redis и геокодера (`test_registration_flow.py` и др.) — без реальной БД. |
| `tests/conftest.py` | Общие переменные окружения для тестов; **autouse**-фикстура отключает реальный вызов `ensure_bucket` при импорте lifespan API, чтобы не требовать MinIO. |

**Запуск всех тестов** (из корня репозитория):

```bash
cd backend && pip install -r requirements-dev.txt
pytest
```

Точечно, например только unit:

```bash
cd backend && pytest tests/unit -q
```

Для интеграционных тестов с подменой зависимостей внешние Postgres/Redis в момент прогона не обязаны, но переменные `DATABASE_URL` и т.д. задаются в `conftest.py` по умолчанию.

---

## Технологии

- Python, **FastAPI**, Pydantic v2, SQLAlchemy 2.0 (async)
- PostgreSQL, Redis, RabbitMQ, MinIO (S3-совместимый), Celery, aiogram (бот)

---

## Запуск (dev)

```bash
# 1. Скопировать и заполнить окружение
cp backend/.env.example backend/.env
# Обязательно: BOT_TOKEN, BOT_SECRET, API_SECRET (совпадают между ботом и API)

# 2. Поднять инфраструктуру, API, бота и воркеры
docker compose up --build

# Миграции выполняет сервис migrate. Документация API: http://localhost:8000/docs
```

### Webhook (prod)

В `backend/.env`:

```
BOT_TRANSPORT=webhook
WEBHOOK_URL=https://bot.yourdomain.com/webhook
WEBHOOK_SECRET_TOKEN=<случайная-строка>
APP_ENV=prod
```

### Без Docker (локально)

```bash
cd backend
pip install -r requirements-dev.txt

# Только инфраструктура в Docker:
docker compose up postgres redis rabbitmq minio -d

alembic upgrade head

# Терминал 1 — API
uvicorn api.main:app --reload

# Терминал 2 — бот
python -m bot.main
```
