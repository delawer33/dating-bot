# Backend – Architecture Notes for AI Agents

## Service boundaries

| Service | Entry point | Responsibility |
|---------|-------------|----------------|
| `api` | `uvicorn api.main:app` | Authoritative REST API. Owns all DB writes and validation. |
| `bot` | `python -m bot.main` | Telegram UI layer. Calls the API; never writes to DB directly. |
| `shared` | imported by both | DB models, session factory, geocoding adapters, base config. |

## Key invariants

- **API is authoritative.** The bot is a thin UI adapter; state transitions go through
  `/registration/*`, `/discovery/*`, `/profile/*`, `/preferences/*` (no direct DB from the bot).
- **Bot FSM is transient.** aiogram FSM state (stored in Redis) reflects conversation
  position. The API infers the canonical step from DB columns at every request.
- **Shared secret.** Every bot→API call must include `X-Bot-Secret: <BOT_SECRET>`.
  `hmac.compare_digest` prevents timing attacks.

## Registration step inference

`registration_step_from_data(...)` lives in `api/services/registration_steps.py` (imported from
`registration_service` for DB-facing code). It uses `users.registration_completed`, `profile`
columns, `photo_count`, `user_preferences`, and `registration_min_photos`. Order after location:
`photos` → `search_preferences` (age, gender list including `[]`, max distance) →
`optional_profile` (bio / interests, skippable) → user calls `POST /registration/complete`.

`is_complete` in API responses is true when `users.registration_completed` is true. Discovery
requires the same flag plus a `user_preferences` row (`api/services/discovery/interactions.py`,
`_require_registered_viewer`).

## Profile photos (MinIO, Telegram `file_id`)

- Shared pipeline: `api/services/profile_photo_service.py` (`add_photo_from_telegram`).
- `POST /registration/photo` during the wizard; `POST /profile/photo` after registration.
- Delete / reorder: `POST /profile/photo/delete`, `POST /profile/photo/reorder`.

The bot always asks the API for the current step on `/start`; it does not own the step
counter in the database.

## Geocoding chain

`CascadeGeocodingProvider` → `NominatimProvider` (primary) → `GoogleMapsProvider` (fallback, opt-in via `GOOGLE_MAPS_API_KEY`).  
To add a new provider: implement the `GeocodingProvider` protocol in `shared/geo/` and add an instance to the cascade list in `api/dependencies.py::build_geocoding_provider`.  
Great-circle distance for discovery filters: `shared/geo/distance.py` (`haversine_km`).

## Transport adapter

`BOT_TRANSPORT=polling` → `PollingAdapter` (dev default).  
`BOT_TRANSPORT=webhook` → `WebhookAdapter` (requires `WEBHOOK_URL`).  
`build_transport()` in `bot/transport/adapter.py` is the single decision point.

**Bot→API HTTP:** `bot/api_client.py` uses one long-lived `httpx.AsyncClient` (`init_api_http` /
`close_api_http` from `bot/main.py`).

## DB schema

Migrations: `alembic upgrade head` (run via the `migrate` compose service).  
Models live in `shared/db/models.py`; always import `Base` from `shared/db/base.py`.  
Never modify `001_initial_schema.py`; create a new revision for every change.

Stage 3 tables (see `004_stage3_discovery_ratings.py`): `profile_interactions`, `matches`,
`user_behavior_stats`, `user_ratings`, `referral_events`.

## Discovery and ratings

- **Discovery** (`api/routers/discovery.py`): `POST /discovery/next|like|skip` — Redis prefetch
  queue `discovery:queue:{viewer_user_id}`, ranking by `user_ratings.combined_score`, filters
  from viewer prefs. Implementation is split under `api/services/discovery/` (`queue.py`,
  `ranking.py`, `interactions.py`); `api/services/discovery_service.py` re-exports the public API.
  After like/skip: RabbitMQ topic `dating.events` (`profile.liked` / `profile.skipped` /
  `match.created`); **`workers/behavior_consumer.py`** updates `user_behavior_stats` and enqueues
  Celery **`rating.recompute_user`**.
- **Ratings**: `api/services/rating_algorithms.py` + `rating_service.recompute_user_rating`;
  Celery app `workers/celery_app.py`, beat task `rating.recompute_all` every 120s.
- **Worker DB bootstrap**: `workers/db.py` (`create_async_engine_and_sessionmaker`) — shared by
  `workers/rating_tasks.py` and `workers/behavior_consumer.py`.
- **Profile card JSON** shared by discovery and “my profile”: `api/services/profile_card.py`
  (`build_profile_card`).

## Bot main menu (reply keyboard)

- **`bot/handlers/menu.py`** — `/menu`, `/profile`, **Анкеты / Мой профиль / Параметры поиска**
  (`~StateFilter(RegistrationStates)`). **Мой профиль** opens a submenu; **Параметры поиска**
  shows summary + edit submenu.
- **`bot/handlers/settings.py`** — per-block profile and preference edits (post-registration);
  router registered **after menu, before registration**.
- **`bot/keyboards.py`** — `MAIN_MENU_KEYBOARD`, profile/search submenus, `BTN_*` constants.
- Shown after registration complete and on `/start` when already complete.

## Referrals

On first successful `POST /registration/complete` (when `registration_completed` becomes true),
idempotent `referral_events` row for `referee_id`; Celery recompute for referee + user
(`registration_service` + `api/services/task_helpers.py`).

## Interests taxonomy

Curated ids in `shared/interests_taxonomy.py` (`VALID_INTEREST_IDS`). Russian labels for the bot
live in `INTEREST_LABELS_RU`.

## Migrate Docker image

Slim `backend/migrate/Dockerfile` + `requirements-migrate.txt`; compose passes **`DATABASE_URL`**
only. **`alembic/env.py`** uses `os.environ["DATABASE_URL"]` when set so migrations do not need
full `SharedConfig`.
