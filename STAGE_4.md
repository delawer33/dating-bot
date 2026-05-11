# Stage 4

## Optimizations

This section records how the backend handles I/O and scaling-related concerns today.

**Discovery ranking and distance** (`api/services/discovery/ranking.py`) — Candidate user ids come from a ranked SQL query. When a max-distance filter applies, candidate coordinates are loaded with a single `SELECT` on `profiles` restricted by `user_id IN (...)`, and distance is evaluated in process with `haversine_km`.

**Discovery inbox and profile cards** (`api/services/discovery/interactions.py`, `api/services/profile_card.py`) — The incoming-likes inbox loads cards through `build_profile_cards_for_users`, which batch-queries profiles and photos for the relevant user ids. Presigned GET URLs go through the `PhotoPresigner` protocol (`api/services/photo_presign.py`): production uses `BotoPhotoPresigner` (wired via `get_photo_presigner` in `api/dependencies.py`), and tests can inject `StubPhotoPresigner` or `None` to skip signing. URLs are resolved in parallel with `asyncio.gather` over `PhotoPresigner.presign` coroutines.

**Registered viewer for discovery** (`api/services/discovery/interactions.py`) — `_require_registered_viewer` returns `(User, UserPreferences)` in one pass so callers that need both (for example `get_next_profile`) use that tuple without a second preferences query.

**Celery rating workers** (`workers/rating_tasks.py`) — Each worker process holds one async SQLAlchemy engine and sessionmaker for rating tasks. `rating.recompute_user` opens a session, runs `recompute_user_rating` inside `session.begin()`, and returns. `rating.recompute_all` uses one `AsyncSession`: after a read transaction collects all user ids that have preferences, each user’s rating is recomputed in its own `session.begin()` on that same session.

**Rating persistence** (`api/services/rating_service.py`) — `recompute_user_rating` loads `User`, `Profile`, `UserPreferences`, and `UserBehaviorStats` in one `SELECT` with `OUTER JOIN`s, and includes the successful-referral count as a scalar subquery in that statement. It then upserts `user_ratings` and reads back the row with `session.get(UserRating, user_id)`. `count_successful_referrals` remains a separate public helper for ad hoc counts.

**Database connection pools** (`shared/config.py`, `shared/db/session.py`, `workers/db.py`) — Pool behaviour is configured via `database_pool_size`, `database_max_overflow`, and `database_pool_recycle` on `SharedConfig` (defaults 5, 10, and 1800 seconds). The API passes these into `init_db` when creating the engine; worker code builds its engine from `SharedConfig` with the same fields.

**Nominatim geocoding** (`shared/geo/nominatim.py`) — `NominatimProvider` keeps a reusable `httpx.AsyncClient` (recreated if closed). `aclose()` closes that client when the host application wants a clean shutdown.

**Discovery Redis queue** (`api/services/discovery/queue.py`) — When the prefetch queue is refilled, `DELETE`, `RPUSH`, and `EXPIRE` for the queue key are issued through a non-transactional Redis pipeline and executed in one round-trip to the server.

## Tests

Automated tests live under `backend/tests/` and are run with pytest from the `backend/` directory (`python -m pytest` or `python -m pytest tests`). `pytest.ini` sets `testpaths = tests`, `asyncio_mode = auto`, and registers the `integration_db` marker.

### Bot authentication on routers

All bot-facing routers (`registration`, `profile`, `preferences`, `discovery`) declare **`dependencies=[Depends(require_bot_auth)]`** on the `APIRouter`. That way `X-Bot-Secret` is validated **before** route-level dependencies such as `DBSession` run, so missing or wrong secrets return **401** without opening a database session. The shared `BotAuth` parameter was removed from individual handlers as redundant.

### Test app without lifespan (`create_app`)

`api/main.py` exposes **`create_app(use_lifespan: bool = True)`**. Production uses `app = create_app(use_lifespan=True)` (default `FastAPI` with DB, MinIO bucket ensure, Redis, and RabbitMQ publisher startup). HTTP hardening tests call **`create_app(use_lifespan=False)`** so the ASGI app mounts the same routers and middleware but **does not** run the startup/shutdown lifespan (no broker, no global `init_db` / `init_redis`). Those tests supply Postgres and Redis only via **`app.dependency_overrides`** for `get_session` and `get_redis`.

### Layout

- **`tests/conftest.py`** — Shared setup: safe default env vars so config does not read production `.env`, autouse patch so API lifespan does not require a real MinIO bucket, helpers for stub DB/Redis sessions, and a fixture that mounts the FastAPI app with session/redis overrides for integration-style tests.
- **`tests/unit/`** — Fast, isolated checks: pure helpers, Pydantic schemas, mocked HTTP/DB, and small slices of workers/bot code without a running broker or database.
- **`tests/integration/`** — HTTP-level checks against the real FastAPI `app` (lifespan still runs). External I/O is avoided by overriding dependencies and/or mocking service functions imported by routers. **`test_bot_auth_http.py`** uses `create_app(use_lifespan=False)` with **no** dependency overrides and asserts **401** on representative `POST` routes when `X-Bot-Secret` is omitted.
- **`tests/integration_db/`** — Service-level and data-layer checks against **real Postgres and Redis** via **testcontainers** (declared in `requirements-dev.txt`). On first use, `alembic upgrade head` is applied to the ephemeral database (`tests/integration_db/migrations.py`). Each test gets an async SQLAlchemy session and a Redis client; teardown truncates `users` (CASCADE) and `FLUSHDB` on Redis. If Docker is unavailable or `INTEGRATION_DB=0` is set in the environment, these tests are **skipped** so the default suite stays green in environments without a Docker daemon. **`test_api_http_stack.py`** exercises **`httpx.AsyncClient` + `ASGITransport`** against `create_app(use_lifespan=False)` with overrides: **`POST /registration/complete`** (factory-built user at `optional_profile` with enough photos), **`POST /discovery/like`** and **`POST /discovery/skip`** end-to-end, plus one **401** case without the bot header (auth still runs before DB).
- **`tests/factories/`** — Builders that insert coherent `User` / `Profile` / `UserPreferences` (+ optional `UserRating`) rows for `integration_db` scenarios. **`insert_user_ready_for_registration_complete`** builds a user who can legally call **`POST /registration/complete`** (search prefs complete, `registration_min_photos` met, core profile fields present).

### What is covered (by area)

| Area | What the tests exercise |
|------|-------------------------|
| **Registration** | Step inference, preference completeness, validation helpers, and a few `/registration/*` flows via `TestClient` with a stubbed async session. **`integration_db`**: `POST /registration/complete` through ASGI with real Postgres and patched `schedule_rating_recompute`. |
| **Discovery (mocked HTTP)** | Distance math, discovery response schemas, and discovery routes with the discovery service layer mocked (next/like/skip/incoming-likes plus auth). |
| **Discovery (`integration_db`)** | `rank_candidate_ids` (gender filter, prior interaction exclusion, max-distance filtering with real coordinates), Redis `pop_next_target_id` refill, `record_like` / duplicate `409`, reciprocal match persistence, `record_skip`. **ASGI HTTP**: `POST /discovery/like` and `POST /discovery/skip` with real DB + Redis and a no-op event publisher override. |
| **Profile & preferences (mocked HTTP)** | Profile “me” and several mutation routes with edit services mocked; preferences age/gender/distance routes similarly. |
| **Profile & preferences (`integration_db`)** | `build_profile_card` with `StubPhotoPresigner`, `get_profile_me`, `edit_age_range`, `edit_display_name`, `count_profile_photos`. |
| **Bot auth (integration)** | Parametrized `POST` routes return **401** when `X-Bot-Secret` is missing, using `create_app(use_lifespan=False)` (no DB connection required). |
| **Photo presign (unit)** | `StubPhotoPresigner` URL shape; `age_on_date` edge cases. |
| **Geocoding** | Cascade provider behavior with `pytest-httpx` (Nominatim/Google paths, errors). |
| **Ratings** | Scoring functions in isolation; persistence `recompute_user_rating` with a mocked SQLAlchemy session; async Celery helper that wraps recompute with mocked engine/session. |
| **Workers** | Telegram notify helper; behavior consumer (histogram merge, event application, dedup + Celery enqueue) with Redis/session mocked. |
| **Bot** | Transport factory (polling vs webhook), API error formatting for the user, menu preference text, `httpx`-mocked bot→API client calls, and circuit breaker / retry helpers. |
| **API infra** | `EventPublisher` guard when not connected; `/health` in integration smoke. |

### Selecting tests

- Full suite (skips `integration_db` when Docker is missing): `python -m pytest tests` from `backend/`.
- Only container-backed tests: `python -m pytest tests/integration_db -m integration_db`.
- Force-disable container tests: `INTEGRATION_DB=0 python -m pytest tests`.

There is no second frontend test tree; coverage is backend-only. RabbitMQ and Celery are still not started for pytest; event publishing in `integration_db` discovery tests uses a lightweight no-op publisher instead of a real broker.
