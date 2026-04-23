# Рекомендации и рейтинг (кратко)

**Лента:** SQL-фильтры зрителя → сортировка по **`combined_score`** → при необходимости **Haversine** + **`max_distance_km`** → первые **10** UUID → Redis `discovery:queue:{viewer_id}` → по одному ID карточка из БД. Redis хранит **только ID**, не JSON анкет.

**Код:** `discovery_service.py` · `rating_algorithms.py` · `rating_service.py`

---

## Соответствие `rating-algos.md` → код

| Уровень (`rating-algos.md`) | В коде |
|----------------------------|--------|
| **Level 1: Primary Rating** (анкета, полнота, фото, preferences) | Один числовой вход: **`completeness_score` / 100** + бонус **+0.02**, если задан **`max_distance_km`** (потолок 1). Отдельные поля анкеты в формулу **не** входят — они уже могут влиять на `completeness_score` при расчёте профиля. |
| **Level 2: Behavioral rating** (лайки, ratio, matches, диалоги, время суток) | Лайки **L**, скипы **S**, матчи **M** из `user_behavior_stats`. **Нет:** диалогов после матча; **histogram по времени** пишется воркером, в скор **не** входит. |
| **Level 3: Combined Rating** + **referral** | Взвешенная сумма **primary** + **behavioral** + **`referral_bonus`**, затем **clamp** в отрезок **0…1**. |

---

## Формулы (`rating_algorithms.py`, `v1.0.0`)

Обозначения: **C** — `completeness_score` (0…100), **L, S, M** — лайки / скипы / матчи «на пользователя», **n** — число успешных рефералов, **eps** = `1e-9` (как в коде).

`clamp(x, lo, hi)` = min(hi, max(lo, x)).

### Level 1 — `primary`

```
base   = clamp(C / 100, 0, 1)
primary = min(1, base + 0.02)   если задан max_distance_km в preferences
primary = base                  иначе
```

### Level 2 — `behavioral`

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

### Referral — `referral_bonus`

**Кому:** пользователю, **чей реферальный код** ввёл приглашённый (реферер). **Когда:** после того как приглашённый (рефери) **успешно завершает регистрацию** (`POST /registration/complete`), в БД появляется строка `referral_events` (одна на рефери: `referrer_id` → реферер, `referee_id` → рефери), и для реферера пересчитывается рейтинг — в формулу входит число таких строк **n** за всё время.

```
referral_bonus = min(0.12, 0.03 * n)
```

### Level 3 — `combined` → `user_ratings.combined_score`

Константы: **`WEIGHT_PRIMARY = 0.42`**, **`WEIGHT_BEHAVIORAL = 0.43`**.

```
raw      = 0.42 * primary + 0.43 * behavioral + referral_bonus
combined = clamp(raw, 0, 1)
```

---

## Обновление рейтинга

- **Поведение и реферал:** лайк / скип / матч → **RabbitMQ** → `behavior_consumer` → счётчики → **Celery** `rating.recompute_user` → upsert **`user_ratings`**.
- **Завершение регистрации:** сразу после commit в `complete_registration` синхронно пересчитываются **`user_ratings`** для **рефери** и (если сработал новый реферал) для **реферера**; параллельно по-прежнему ставится задача в Celery для согласованности.

---

## Не в скоре

**Level 2** из спеки: *dialog after match*, *time-of-day в формуле*.
