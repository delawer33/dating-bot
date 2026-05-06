# ОТЧЁТ

## Цель

Показать на практике, что при параллельной работе с БД возникают аномалии изоляции.

## СУБД

Используется **MariaDB (InnoDB)** в Docker. Причина: в MariaDB можно воспроизвести `dirty read` на уровне изоляции `READ UNCOMMITTED` (в PostgreSQL `dirty read` не воспроизводится).

## Файлы

- SQL-скрипты:
  - `sql/00_schema.sql` — таблицы;
  - `sql/01_seed.sql` — тестовые данные.
- Docker стенд: `docker-compose.yml`
- Скрипты воспроизведения:
  - `scripts/dirty_read.py`
  - `scripts/non_repeatable_read.py`
  - `scripts/phantom_read.py`
  - `scripts/lost_update.py`
  - `scripts/run_all.py` — прогоняет всё подряд

## Как запустить

Все “скриншоты” — это логи из терминала (с таймстампами) + итоговые значения в таблицах.

Из папки `tasks/sql-isolation`:

1) Поднять БД:

```bash
docker compose up -d db
```

2) Прогнать SQL (схема + тестовые данные) через `docker compose run`:

```bash
docker compose run --rm db sh -lc "mariadb -uapp -papp -h db isolation < /work/sql/00_schema.sql"
docker compose run --rm db sh -lc "mariadb -uapp -papp -h db isolation < /work/sql/01_seed.sql"
```

2) Запустить все сценарии:

```bash
docker compose run --rm runner
```

Или запускать по одному:

```bash
docker compose run --rm runner bash -lc "pip install -r requirements.txt && python scripts/dirty_read.py"
docker compose run --rm runner bash -lc "pip install -r requirements.txt && python scripts/non_repeatable_read.py"
docker compose run --rm runner bash -lc "pip install -r requirements.txt && python scripts/phantom_read.py"
docker compose run --rm runner bash -lc "pip install -r requirements.txt && python scripts/lost_update.py"
```


## Подготовка данных

Таблицы:

- `notes(id, value)` — для `dirty read`
- `accounts(id, owner, balance)` — для `non-repeatable read` и `lost update`
- `orders(id, amount)` — для `phantom read`

Начальные данные задаются в `sql/01_seed.sql`:

- `notes.value(id=1)=10`
- `accounts`: `alice=100`, `bob=100`
- `orders.amount`: `50`, `150`, `200`

---

## Аномалия 1 — Dirty Read (грязное чтение)

### Суть
Транзакция **T2** читает данные, которые **T1** изменила, но ещё **не зафиксировала**. Если T1 сделает `ROLLBACK`, то T2 фактически читала то, чего “никогда не было”.

### Условия
- Уровень изоляции: `READ UNCOMMITTED` (в MariaDB допускает грязные чтения)

### Две параллельные транзакции (реальный SQL-плейбук)

**Шаг 1 — T1 (Транзакция 1):**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;
```

**Шаг 2 — T1:**

```sql
SELECT value FROM notes WHERE id=1;  -- 10
UPDATE notes SET value = 999 WHERE id=1;  -- НЕ коммитим
```

**Шаг 3 — T2 (Транзакия 2):**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;
SELECT value FROM notes WHERE id=1;  -- 999 (dirty read)
```

**Шаг 4 — T1:**

```sql
ROLLBACK;
```

**Шаг 5 — T2:**

```sql
SELECT value FROM notes WHERE id=1;  -- 10 (после rollback в T1)
COMMIT;
```

### Шаги воспроизведения
Запуск:

```bash
docker compose run --rm runner bash -lc "pip install -r requirements.txt && python scripts/dirty_read.py"
```

### Полученный результат (что должно быть в логах)

- Внутри T2 первый `SELECT` показывает `999`, хотя T1 ещё не делала `COMMIT`
- После `ROLLBACK` в T1 повторный `SELECT` показывает `10`
- Итог в БД: `notes.value(id=1)=10`

### Как избежать

- Использовать **не ниже `READ COMMITTED`** (грязные чтения будут запрещены).
- Не включать `READ UNCOMMITTED` в боевых системах (исключение — очень специфичные сценарии аналитики/кэшей, где это осознанный компромисс).

---

## Аномалия 2 — Non-repeatable Read (неповторяемое чтение)

### Суть
Транзакция **T1** дважды читает одну и ту же строку и получает **разные значения**, потому что параллельная транзакция **T2** изменила и закоммитила эту строку между чтениями T1.

### Условия
- Уровень изоляции: `READ COMMITTED`

### Две параллельные транзакции (реальный SQL-плейбук)

**Шаг 1 — T1:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
SELECT balance FROM accounts WHERE owner = 'alice'; -- 100
```

**Шаг 2 — T2:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
UPDATE accounts SET balance = balance + 50 WHERE owner = 'alice';
COMMIT;
```

**Шаг 3 — T1:**

```sql
SELECT balance FROM accounts WHERE owner = 'alice'; -- 150 (non-repeatable read)
COMMIT;
```

### Шаги воспроизведения

```bash
docker compose run --rm runner bash -lc "pip install -r requirements.txt && python scripts/non_repeatable_read.py"
```


### Полученный результат

- В T1 два `SELECT` подряд (в рамках одной транзакции) показывают разные значения баланса `alice`.
- Итог в БД: `balance(alice)=150`.

### Как избежать

- Перейти на `REPEATABLE READ` (или выше), где чтения в одной транзакции “стабилизируются” снапшотом.
- Или использовать блокировки на чтение там, где важно “не менялось”: `SELECT ... FOR UPDATE` / `LOCK IN SHARE MODE` (зависит от СУБД и кейса).
- На уровне приложения — проектировать операции так, чтобы повторное чтение не воспринималось как инвариант, если он не гарантируется изоляцией.

---

## Аномалия 3 — Phantom Read (фантомное чтение)

### Суть
Транзакция **T1** дважды выполняет запрос по условию (например, `COUNT(*) WHERE ...`) и получает **разный набор строк / разный COUNT**, потому что другая транзакция **T2** вставила новые строки, подходящие под условие, и закоммитила их.

### Условия
- Уровень изоляции: `READ COMMITTED`

### Две параллельные транзакции (реальный SQL-плейбук)

В двух терминалах открыть клиент:

```bash
docker compose run --rm db mariadb -uapp -papp -h db isolation
```

Дальше выполнять **в строгом порядке (как в логах)**:

**Шаг 1 — T1:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
SELECT COUNT(*) FROM orders WHERE amount >= 100; -- 2
```

**Шаг 2 — T2:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
INSERT INTO orders(amount) VALUES (120);
COMMIT;
```

**Шаг 3 — T1:**

```sql
SELECT COUNT(*) FROM orders WHERE amount >= 100; -- 3 (phantom read)
COMMIT;
```

### Шаги воспроизведения

```bash
docker compose run --rm runner bash -lc "pip install -r requirements.txt && python scripts/phantom_read.py"
```

### Полученный результат

- В T1 дважды считается `COUNT(amount>=100)`, второй раз больше на 1.
- Итог в БД: `COUNT(amount>=100)=3`.

### Как избежать

- Использовать более строгую изоляцию (`REPEATABLE READ` / `SERIALIZABLE`) — зависит от СУБД и требований.
- Использовать блокировки/предикатные блокировки (если поддерживаются) или “locking reads” для диапазона.
- На уровне логики — не полагаться на повторный `COUNT` как на инвариант в слабых уровнях изоляции; при необходимости “фиксировать” набор (например, материализацией списка ключей в начале транзакции).

---

## Аномалия 4 — Lost Update (потерянное обновление)

### Суть
Две транзакции одновременно делают read-modify-write без координации:

1) обе читают одно и то же значение,
2) обе рассчитывают новое значение,
3) обе записывают,

в итоге обновление одной транзакции “затирает” другую.

### Условия
- Уровень изоляции: `READ COMMITTED`
- Ключевой момент: **обновление делается “значением”, а не атомарной операцией**.

### Две параллельные транзакции (реальный SQL-плейбук)

В двух терминалах открыть клиент:

```bash
docker compose run --rm db mariadb -uapp -papp -h db isolation
```

Дальше выполнять **в строгом порядке (как в логах)**:

**Шаг 0 (проверка старта, в любой сессии):**

```sql
SELECT balance FROM accounts WHERE owner = 'bob'; -- 100
```

**Шаг 1 — T1:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
SELECT balance FROM accounts WHERE owner = 'bob'; -- 100
```

**Шаг 2 — T2:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
SELECT balance FROM accounts WHERE owner = 'bob'; -- 100
```

**Шаг 3 — T2:**

```sql
UPDATE accounts SET balance = 110 WHERE owner = 'bob';
COMMIT;
```

**Шаг 4 — T1:**

```sql
UPDATE accounts SET balance = 110 WHERE owner = 'bob';
COMMIT;
```

**Шаг 5 (проверка итога, в любой сессии):**

```sql
SELECT balance FROM accounts WHERE owner = 'bob'; -- 110 (ожидали 120 => lost update)
```

### Шаги воспроизведения

```bash
docker compose run --rm runner bash -lc "pip install -r requirements.txt && python scripts/lost_update.py"
```

### Полученный результат

- В логах видно, что обе транзакции прочитали `100`.
- Итог в БД: `balance(bob)=110`.
- В скрипте также печатается: “Ожидали 120, но получили 110 => lost update”.

### Как избежать

- Делать **атомарные обновления** на стороне БД:
  - вместо read-modify-write: `UPDATE accounts SET balance = balance + 10 WHERE owner='bob'`
- Или использовать **пессимистическую блокировку**:
  - `SELECT ... FOR UPDATE`, затем вычисление и `UPDATE`
- Или **оптимистическую конкуренцию** (version / CAS):
  - `UPDATE ... SET balance=?, version=version+1 WHERE id=? AND version=?` и при 0 affected rows — ретрай.

---

## Вывод

На одном и том же наборе данных показаны 4 аномалии:

- `dirty read` (на `READ UNCOMMITTED`)
- `non-repeatable read` (на `READ COMMITTED`)
- `phantom read` (на `READ COMMITTED`)
- `lost update` (read-modify-write без координации)


- При низких уровнях изоляции чтение может увидеть **незафиксированные** данные (`dirty read`), а при `READ COMMITTED` — **меняющиеся** результаты повторных запросов (`non-repeatable`, `phantom`).
- `lost update` возникает не “из-за SELECT”, а из-за шаблона **read → вычисление → запись computed-value** без блокировок/проверок.
- Практические способы защиты: поднять изоляцию (минимум `READ COMMITTED`, при необходимости `REPEATABLE READ`/`SERIALIZABLE`), использовать `SELECT ... FOR UPDATE` для критичных строк/диапазонов, и по возможности делать **атомарные UPDATE** или **оптимистическую конкуренцию** (version/CAS + retry).

