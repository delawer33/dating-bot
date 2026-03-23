# Схема БД (PostgreSQL)

## ER diagram (overview)

```mermaid
erDiagram
  users ||--o| profiles : has
  users ||--o| user_preferences : has
  profiles ||--o{ profile_photos : has
  users ||--o{ profile_interactions : acts
  users ||--o{ profile_interactions : receives
  users ||--o{ matches : participates
  users ||--o| user_behavior_stats : has
  users ||--o| user_ratings : has
  users ||--o{ referral_events : refers
  users }o--o| users : referred_by
```

## Таблицы

### `users`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID | PK, default `gen_random_uuid()` |
| `telegram_id` | BIGINT | UNIQUE, NOT NULL |
| `username` | TEXT | Nullable; Telegram @ без @ |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now |
| `is_active` | BOOLEAN | NOT NULL, default true |
| `referral_code` | TEXT | UNIQUE, human-shareable |
| `referred_by_user_id` | UUID | FK → `users(id)`, nullable |

**Indexes:** `UNIQUE(telegram_id)`, `UNIQUE(referral_code)`.

### `profiles`

Одна строка на пользователя (1:1). Discovery filters используют эти колонки.

| Column | Type | Notes |
|--------|------|--------|
| `user_id` | UUID | PK/FK → `users(id)` ON DELETE CASCADE |
| `display_name` | TEXT | |
| `bio` | TEXT | |
| `birth_date` | DATE | Лучше, чем голый возраст (age drift) |
| `gender` | TEXT or ENUM | Должен совпадать с app enums |
| `city` | TEXT | Display / filter; из geocoder или curated list |
| `district` | TEXT | Nullable; borough/suburb/admin subdivision внутри `city` |
| `latitude` | DOUBLE PRECISION | Nullable |
| `longitude` | DOUBLE PRECISION | Nullable |
| `interests` | JSONB | Позже можно нормализовать в `user_interests` + `interests` |
| `completeness_score` | SMALLINT | 0–100, поддерживается API/Celery |
| `updated_at` | TIMESTAMPTZ | |

**Indexes:** `(city)`, `(city, district)` если discovery фильтрует по area; `(gender)` при частой фильтрации; позже GiST `(latitude, longitude)` или PostGIS.

### `profile_photos`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID | PK |
| `profile_id` | UUID | FK → `profiles(user_id)` |
| `s3_key` | TEXT | NOT NULL |
| `sort_order` | INT | NOT NULL, default 0 |
| `created_at` | TIMESTAMPTZ | |

**Indexes:** `(profile_id, sort_order)`.


### `user_preferences`

| Column | Type | Notes |
|--------|------|--------|
| `user_id` | UUID | PK/FK → `users(id)` |
| `age_min` | SMALLINT | |
| `age_max` | SMALLINT | |
| `gender_preferences` | TEXT[] or ENUM[] | |
| `max_distance_km` | INT | Nullable; Предпочтение по максимальной дистанции поиска |
| `updated_at` | TIMESTAMPTZ | |

### `profile_interactions`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID | PK |
| `actor_user_id` | UUID | FK → `users` |
| `target_user_id` | UUID | FK → `users` |
| `action` | ENUM | `like`, `skip` |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now |

**Indexes:** `(actor_user_id, created_at DESC)`, `(target_user_id, created_at DESC)`, `(target_user_id, action)`.

### `matches`

**Pair ordering:** всегда сохранять пару в фиксированном порядке, чтобы `(A,B)` и `(B,A)` были одной строкой — например `user_a_id` = меньший UUID, `user_b_id` = больший UUID (одно правило `LEAST` / `GREATEST` везде, включая publish `match.created`).

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID | PK; стабильный id для этого match |
| `user_a_id` | UUID | FK → `users`; первый user в canonical order |
| `user_b_id` | UUID | FK → `users`; второй user в canonical order |
| `created_at` | TIMESTAMPTZ | Когда создана строка match (вторая сторона mutual like) |

**Indexes:** `UNIQUE(user_a_id, user_b_id)`.

### `user_behavior_stats`

Аггрегаты, поддерживаются воркерами

| Column | Type | Notes |
|--------|------|--------|
| `user_id` | UUID | PK/FK |
| `likes_received` | INT | default 0 |
| `skips_received` | INT | default 0 |
| `views_implied` | INT | Nullable если показы не трекаются |
| `matches_count` | INT | default 0 |
| `activity_histogram` | JSONB | Optional hour-of-week buckets (например из interaction timestamps) |
| `updated_at` | TIMESTAMPTZ | |

### `user_ratings`

Отдельная таблица пересчитанных score (Celery).

| Column | Type | Notes |
|--------|------|--------|
| `user_id` | UUID | PK/FK |
| `primary_score` | DOUBLE PRECISION | Level 1 |
| `behavioral_score` | DOUBLE PRECISION | Level 2 |
| `referral_bonus` | DOUBLE PRECISION | Level 3 add-on |
| `combined_score` | DOUBLE PRECISION | Final |
| `breakdown` | JSONB | Optional component detail |
| `algorithm_version` | TEXT | например `v1.0.0` |
| `computed_at` | TIMESTAMPTZ | |

**Indexes:** `(combined_score DESC)`

### `referral_events` (audit)

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID | PK |
| `referrer_id` | UUID | FK |
| `referee_id` | UUID | FK |
| `credited_at` | TIMESTAMPTZ | |
