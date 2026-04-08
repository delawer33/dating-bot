# Profile API – Registration Endpoints (Stage 2)

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
  "message": ""
}
```

---

## POST /registration/display-name

**Request**
```json
{ "telegram_id": 123456789, "display_name": "John Doe" }
```

**Response** `200` – same shape as above, `registration_step` advances to `"birth_date"`.

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

## POST /registration/complete

Validates all required fields, creates default `user_preferences`, sets `completeness_score`.

**Request**
```json
{ "telegram_id": 123456789 }
```

**Response** `200` – `registration_step: "complete"`, `is_complete: true`

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
| 409 | Step already completed |
| 422 | Validation error or geocoding failure |
