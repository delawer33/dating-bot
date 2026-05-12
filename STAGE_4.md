# Stage 4

## Logging

Structured logging is configured in **`shared/logging_setup.py`**: one process-wide root handler, a per-service label (`api`, `bot`, `behavior-consumer`, `celery-worker`, `celery-beat`), and optional **`X-Request-ID`** correlation on the FastAPI app.

**Configuration** (`SharedConfig` in `shared/config.py`, env-backed): **`LOG_LEVEL`** (default `INFO`), **`LOG_JSON`** (optional boolean; when unset, JSON lines are used only when **`APP_ENV=prod`**). See `backend/.env.example`.

**API** (`api/main.py`): calls `configure_logging` before other imports that emit logs. **`api/middleware/request_context.py`** registers `RequestContextMiddleware` after CORS: accepts or generates `X-Request-ID`, attaches it to responses, sets a `contextvars` scope for the request so log lines include `rid=…` in text mode or `request_id` in JSON mode, logs one **`http_request`** line per response (skipped for **`GET /health`** to keep probes quiet), and logs **`unhandled_exception`** before re-raising for true 500s. Uvicorn access logging is disabled in **`api/Dockerfile`** (`--no-access-log`) so access lines are not duplicated.

**Bot** (`bot/main.py`) and **RabbitMQ behavior consumer** (`workers/behavior_consumer.py`) each call `configure_logging` at startup with the same env-driven level and JSON policy. **Celery** (`workers/celery_app.py`) attaches **`worker_init`** and **`beat_init`** signals so worker and beat processes configure logging after the prefork pool is up.

**Auth failures**: `require_bot_auth` in `api/dependencies.py` logs **`bot_auth_failed`** at warning (never logs the secret).

**Tests**: `tests/conftest.py` sets **`LOG_LEVEL=WARNING`** by default to reduce noise. Unit tests for helpers live in **`tests/unit/test_logging_setup.py`**.

## Metrics (Prometheus + Grafana)

The API exposes **`GET /metrics`** (Prometheus text format) when **`METRICS_ENABLED`** is true (**`APIConfig`** in `api/config.py`, default **true**). Implementation: **`api/metrics.py`**.

**HTTP:** **`http_requests_total`** `{method,path,status}`, **`http_request_duration_seconds`** histogram `{method,path}`, **`http_requests_in_progress`** gauge (excludes **`GET /metrics`**). **`PrometheusMetricsMiddleware`** records **after** routing so **`path`** is the OpenAPI template. **`GET /metrics`** is excluded from HTTP middleware counts; access logs skip **`/metrics`** (see Logging).

**Domain / infra:** **`event_publish_total`** `{event_type,result}` (`success` / `failure`) on RabbitMQ publish in **`api/messaging/events.py`**. **`bot_auth_failures_total`** on failed **`X-Bot-Secret`** in **`api/dependencies.py`**. **`discovery_actions_total`** `{operation,outcome}` for discovery feed and commits (`next`/`empty`|`profile`, `like`/`committed`, `skip`/`committed`) in **`api/services/discovery/interactions.py`**. **`geocode_reverse_attempts_total`** `{provider,outcome}` via optional hook **`shared/geo/cascade.py`** (`set_geocode_metrics_hook`), wired from **`api/main.py`** lifespan. **DB pool** gauges (**`db_pool_connections_checked_out`**, **`db_pool_connections_size`**, **`db_pool_overflow`**) refreshed on each **`/metrics`** scrape from **`shared/db/session.py::db_pool_stats`**.

Tests: **`create_app(..., enable_metrics=False)`** omits **`/metrics`** and middleware. **`tests/unit/test_api_metrics.py`**, **`tests/unit/test_geocoding.py`** (cascade metrics hook).

### Grafana (Docker Compose profile `observability`)

**Prometheus** (`observability/prometheus.yml`) scrapes every 15s:

| Job | Target | Notes |
|-----|--------|--------|
| `dating-api` | `api:8000/metrics` | Application metrics |
| `postgres` | `postgres_exporter:9187` | **`postgres_exporter`** service (same profile); DB user/password match **`postgres`** |
| `rabbitmq` | `rabbitmq:15692` | **`rabbitmq_prometheus`** plugin enabled in **`observability/docker/rabbitmq/Dockerfile`** (image builds from official `rabbitmq:3-management-alpine`) |
| `minio` | `minio:9000/minio/v2/metrics/cluster` | Compose sets **`MINIO_PROMETHEUS_AUTH_TYPE=public`** so Prometheus can scrape without a bearer token (**dev-only risk**; see **`observability/README.md`**) |

**Grafana** provisions the Prometheus datasource (`uid: **prometheus**`) and file dashboards under **`observability/grafana/dashboards/`**:

- **`dating-api.json`** — project dashboard (HTTP, events, discovery, pool, …).
- **`postgres-overview.json`** — Grafana.com **9628** (PostgreSQL / `postgres_exporter`), normalized for datasource uid `prometheus`.
- **`rabbitmq-overview.json`** — Grafana.com **10991** (RabbitMQ / `rabbitmq_prometheus`).
- **`minio-overview.json`** — Grafana.com **13502** (MinIO Prometheus metrics).

Re-download and normalize the three community exports: **`python3 observability/scripts/normalize_grafana_dashboards.py`**. Overview: **`observability/README.md`**.

From the repo root:

```bash
docker compose --profile observability up -d
```

- Prometheus: **http://localhost:9090**  
- Grafana: **http://localhost:3000** (default login **admin** / **admin**; change in production)

The default **`docker compose up`** stack is unchanged; add **`--profile observability`** when you want Prometheus and Grafana. **RabbitMQ** is now a small custom build (adds the Prometheus plugin and exposes **15692**); other services are unchanged aside from MinIO’s metrics env.

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
| **Profile & preferences (`integration_db`)** | `build_profile_card` with `StubPhotoPresigner`, `get_profile_me`, `edit_age_range`, `edit_display_name`, `count_profile_photos`. **`test_profile_preferences_edit_db.py`**: post-registration profile edits (bio/location/interests limits, photo delete/reorder, preferences 403/404/validation). |
| **Registration (`integration_db`)** | **`test_registration_wizard_db.py`**: full wizard through `complete_registration` on real Postgres with geocoder and Telegram upload mocked. |
| **Registration routes (integration)** | **`test_registration_routes_smoke.py`**: every `POST /registration/*` handler hit with stub session + patched `registration_service` (router line coverage). |
| **Bot auth (integration)** | Parametrized `POST` routes return **401** when `X-Bot-Secret` is missing, using `create_app(use_lifespan=False)` (no DB connection required). |
| **Photo presign (unit)** | `StubPhotoPresigner` URL shape; `age_on_date` edge cases. |
| **Geocoding** | Cascade provider behavior with `pytest-httpx` (Nominatim/Google paths, errors). |
| **Ratings** | Scoring functions in isolation; persistence `recompute_user_rating` with a mocked SQLAlchemy session; async Celery helper that wraps recompute with mocked engine/session. |
| **Workers** | Telegram notify helper; behavior consumer (histogram merge, event application, dedup + Celery enqueue) with Redis/session mocked. |
| **Bot** | Transport factory (polling vs webhook), API error formatting for the user, menu preference text, `httpx`-mocked bot→API client calls, and circuit breaker / retry helpers. |
| **API infra** | `EventPublisher` guard when not connected; `/health` in integration smoke. |

### Coverage (dev gate)

`backend/pyproject.toml` configures **Coverage.py** for the combined tree **`api/` + `shared/` + `workers/`** (the bot package is measured separately if you add `--cov=bot`). `fail_under = 85` applies when you run pytest with `--cov=api --cov=shared --cov=workers`. CI runs that command so merges stay above the threshold. Telegram handlers (`bot/handlers/*`) remain mostly out of this percentage by design; critical persistence and workers are in scope.

### Selecting tests

- Full suite (skips `integration_db` when Docker is missing): `python -m pytest tests` from `backend/`.
- Only container-backed tests: `python -m pytest tests/integration_db -m integration_db`.
- Force-disable container tests: `INTEGRATION_DB=0 python -m pytest tests`.

There is no second frontend test tree; coverage is backend-only. RabbitMQ and Celery are still not started for pytest; event publishing in `integration_db` discovery tests uses a lightweight no-op publisher instead of a real broker.
