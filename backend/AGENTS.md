# Backend – Architecture Notes for AI Agents

## Service boundaries

| Service | Entry point | Responsibility |
|---------|-------------|----------------|
| `api` | `uvicorn api.main:app` | Authoritative REST API. Owns all DB writes and validation. |
| `bot` | `python -m bot.main` | Telegram UI layer. Calls the API; never writes to DB directly. |
| `shared` | imported by both | DB models, session factory, geocoding adapters, base config. |

## Key invariants

- **API is authoritative.** The bot is a thin UI adapter; all state transitions happen via
  `/registration/*` endpoints.
- **Bot FSM is transient.** aiogram FSM state (stored in Redis) reflects conversation
  position. The API infers the canonical step from DB columns at every request.
- **Shared secret.** Every bot→API call must include `X-Bot-Secret: <BOT_SECRET>`.
  `hmac.compare_digest` prevents timing attacks.

## Registration step inference

`_infer_step(profile)` in `api/services/registration_service.py`:

```
profile is None or display_name is None → "display_name"
birth_date is None                       → "birth_date"
gender is None                           → "gender"
city is None                             → "location"
all set                                  → "complete"
```

The bot always asks the API for the current step on `/start`; it never maintains its own
step counter.

## Geocoding chain

`CascadeGeocodingProvider` → `NominatimProvider` (primary) → `GoogleMapsProvider` (fallback, opt-in via `GOOGLE_MAPS_API_KEY`).  
To add a new provider: implement the `GeocodingProvider` protocol in `shared/geo/` and add an instance to the cascade list in `api/dependencies.py::build_geocoding_provider`.

## Transport adapter

`BOT_TRANSPORT=polling` → `PollingAdapter` (dev default).  
`BOT_TRANSPORT=webhook` → `WebhookAdapter` (requires `WEBHOOK_URL`).  
`build_transport()` in `bot/transport/adapter.py` is the single decision point.

## DB schema

Migrations: `alembic upgrade head` (run via the `migrate` compose service).  
Models live in `shared/db/models.py`; always import `Base` from `shared/db/base.py`.  
Never modify `001_initial_schema.py`; create a new revision for every change.
