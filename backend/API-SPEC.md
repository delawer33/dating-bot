# Profile API – Bot-authenticated endpoints (Stages 2–3)

All endpoints require the header:
```
X-Bot-Secret: <BOT_SECRET>
```

Base URL (dev): `http://localhost:8000`

---

## POST /registration/start

Upsert user on first `/start`. Captures referral code once.

**Request**
```json
{
  "telegram_id": 123456789,
  "username": "john",
  "referral_code": "ABC12345"
}
```

**Response** `200`
```json
{
  "user_id": "uuid",
  "telegram_id": 123456789,
  "registration_step": "display_name",
  "is_complete": false,
  "is_new_user": true,
  "photo_count": 0,
  "message": ""
}
```

`is_complete` is true only when `users.registration_completed` is true (wizard finished via `POST /registration/complete`).

---

## POST /registration/display-name

**Request**
```json
{ "telegram_id": 123456789, "display_name": "John Doe" }
```

**Response** `200` – same shape as start; `registration_step` advances.

---

## POST /registration/birth-date

**Request**
```json
{ "telegram_id": 123456789, "birth_date": "1990-01-15" }
```

Validation: must be in the past, user must be ≥ 18.

---

## POST /registration/gender

**Request**
```json
{ "telegram_id": 123456789, "gender": "male" }
```

Allowed values: `male | female | non_binary | other`

---

## POST /registration/location

**Request**
```json
{ "telegram_id": 123456789, "latitude": 55.7558, "longitude": 37.6173 }
```

API reverse-geocodes via Nominatim → Google fallback.  
Returns `422` if geocoding fails.

---

## POST /registration/photo

**Request**
```json
{ "telegram_id": 123456789, "file_id": "<telegram_photo_file_id>" }
```

Stores image in S3, inserts `profile_photos`. Allowed while step is `photos`, `search_preferences`, or `optional_profile` (until max photos).

---

## POST /registration/search-preferences/age-range

**Request**
```json
{ "telegram_id": 123456789, "age_min": 18, "age_max": 35 }
```

Upserts `user_preferences` during step `search_preferences`.

---

## POST /registration/search-preferences/gender

**Request**
```json
{ "telegram_id": 123456789, "gender_preferences": ["male", "female"] }
```

Use `[]` for “any gender”. Field must be present (empty list allowed).

---

## POST /registration/search-preferences/distance

**Request**
```json
{ "telegram_id": 123456789, "max_distance_km": 50 }
```

Bounded by `preferences_max_distance_km` in config (default 500).

---

## POST /registration/bio

Optional step `optional_profile`.

**Request**
```json
{ "telegram_id": 123456789, "bio": "..." }
```

---

## POST /registration/interests

**Request**
```json
{ "telegram_id": 123456789, "interest_ids": ["music", "travel"] }
```

Ids must belong to the server taxonomy (`shared/interests_taxonomy.py`).

---

## POST /registration/complete

Requires: core profile fields, min photos, full search preferences (`age_min`, `age_max`, `gender_preferences` including `[]`, `max_distance_km`), and current step `optional_profile`.

Sets `users.registration_completed = true`, `completeness_score`, referral side-effects as before.

**Request**
```json
{ "telegram_id": 123456789 }
```

**Response** `200` – `registration_step: "complete"`, `is_complete: true`

---

## POST /registration/referral

Returns the caller’s stable `users.referral_code`. If the row had no code (legacy), the API assigns one. Optional `invite_link` is set when `TELEGRAM_BOT_USERNAME` is configured in the API environment (`https://t.me/<username>?start=<referral_code>`).

**Request**
```json
{ "telegram_id": 123456789 }
```

**Response** `200`
```json
{
  "referral_code": "A1B2C3D4",
  "invite_link": "https://t.me/my_dating_bot?start=A1B2C3D4"
}
```

`invite_link` may be `null` if the bot username is not configured.

**Errors** `404` — user not found (call `/registration/start` first).

---

## POST /profile/me

Current user snapshot: registration step, discovery-style profile card (+ `completeness_score` + `interests` + photo `id` per item), preferences when row exists.

**Request**
```json
{ "telegram_id": 123456789 }
```

**Response** `200` — `user_id`, `is_complete`, `registration_step`, `profile`, `preferences`.

---

## POST /profile/* (post-registration edits)

Require `registration_completed`. Each returns `{ "ok": true, "message": "..." }`.

| Method | Path | Body fields |
|--------|------|-------------|
| POST | `/profile/display-name` | `telegram_id`, `display_name` |
| POST | `/profile/birth-date` | `telegram_id`, `birth_date` |
| POST | `/profile/gender` | `telegram_id`, `gender` |
| POST | `/profile/location` | `telegram_id`, `latitude`, `longitude` — clears viewer discovery Redis queue |
| POST | `/profile/bio` | `telegram_id`, `bio` |
| POST | `/profile/interests` | `telegram_id`, `interest_ids` |
| POST | `/profile/photo` | `telegram_id`, `file_id` |
| POST | `/profile/photo/delete` | `telegram_id`, `photo_id` (UUID) |
| POST | `/profile/photo/reorder` | `telegram_id`, `photo_ids` (all photos, new order) |

---

## POST /preferences/* (post-registration)

Require `registration_completed`. Returns `{ "ok": true, "message": "..." }`.

| Path | Body |
|------|------|
| `/preferences/age-range` | `telegram_id`, `age_min`, `age_max` |
| `/preferences/gender` | `telegram_id`, `gender_preferences` |
| `/preferences/max-distance` | `telegram_id`, `max_distance_km` |

---

## POST /discovery/next

Requires `registration_completed` and `user_preferences`. Redis prefetch + ranked candidates.

**Request** `{ "telegram_id": 123456789 }`

**Response** — `profile` (same card shape as discovery; `photos` ordered by `sort_order`) or `exhausted: true`.

---

## POST /discovery/like | /discovery/skip

**Request** `{ "telegram_id", "target_user_id" }` (UUID).

Like may create `matches` row and publish `match.created`. Publishes to RabbitMQ after DB commit.
`409` if pair already interacted.

**Like response** `200` — when `matched: true`, also includes contact for the peer (`target_user_id`):

- `peer_display_name` — display name from profile
- `peer_username` — Telegram `@username` if set, else `null`
- `peer_telegram_id` — numeric Telegram user id

When `matched: false`, `peer_telegram_id` and `peer_username` are `null`.

---

## POST /discovery/incoming-likes

**Request**

```json
{
  "telegram_id": 123456789,
  "mode": "inbox",
  "limit": 10
}
```

- **`mode`** — `"inbox"` (default) or `"history"`.
- **`limit`** — for `history`, `1…100` (default `10`). For `inbox`, the server returns **at most 10** pending likers regardless of `limit`.

**`mode=inbox` (входящие)** — people who liked you, **no** `matches` row yet, and **you** have not yet created any `profile_interactions` row as **actor** toward them (no like/skip back). Each item includes a full discovery-style **`profile`** object (same shape as `/discovery/next`, including presigned photo URLs when S3 is configured). Telegram `actor_*` contact fields stay `null` here (use like/match flow for contact).

**`mode=history` (полная история)** — all likes toward you (newest first), with `is_matched` and optional `actor_telegram_id` / `actor_username` when matched. **`profile`** is always `null` (text-only list in the bot).

Example **history** item:

```json
{
  "interaction_id": "uuid",
  "actor_user_id": "uuid",
  "created_at": "2026-01-01T12:00:00+00:00",
  "actor_display_name": "Имя",
  "is_matched": true,
  "actor_telegram_id": 123456789,
  "actor_username": "nickname",
  "profile": null
}
```

`403` / `404` same as other discovery routes.

---

## GET /health

No auth required.

**Response** `200`
```json
{ "status": "ok", "env": "dev" }
```

---

## Error format

```json
{ "detail": "Human-readable error message" }
```

| Status | Meaning |
|--------|---------|
| 401 | Missing or wrong `X-Bot-Secret` |
| 404 | User not found (call `/start` first) |
| 409 | Step already completed / registration already completed where forbidden |
| 403 | Discovery or settings: registration not complete |
| 422 | Validation error or geocoding failure |
