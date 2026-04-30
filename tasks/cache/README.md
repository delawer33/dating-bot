# Cache Comparison Practice — Report

## Цель и постановка эксперимента

Цель практики — сравнить три стратегии кеширования одной и той же системы в одинаковых условиях:

- `Lazy Loading / Cache-Aside`;
- `Write-Through`;
- `Write-Back`.

Сравнение проводится по метрикам производительности и нагрузки на БД, чтобы понять, какую стратегию выбирать под разные профили трафика.

## Конфигурация стенда

- Приложение: `FastAPI`.
- Кеш: `Redis`.
- База данных: `PostgreSQL`.
- Генератор нагрузки: асинхронный Python-скрипт (`httpx`), запускается в отдельном контейнере.
- Набор данных: 100 сущностей (`id=1..100`).
- Объем нагрузки: 500 запросов на каждый прогон.

## Реализованные стратегии

### 1) Lazy Loading / Cache-Aside

- Чтение: сначала попытка из кеша.
- Если в кеше нет данных, читаем из БД и записываем в кеш.
- Запись: сразу в БД (кеш на запись не обновляется).

Ожидание: хорош для чтения при стабильном рабочем наборе, но в write-heavy может терять hit rate из-за отсутствия прогрева кеша на запись.

### 2) Write-Through

- Чтение: через кеш.
- Запись: синхронно и в БД, и в кеш.

Ожидание: стабильный hit rate и предсказуемое поведение в mixed/write-heavy, но цена — более тяжелый путь записи.

### 3) Write-Back

- Чтение: через кеш.
- Запись: сначала в кеш.
- В БД данные отправляются позже фоновым flush-процессом.

Ожидание: минимальная задержка на запись и низкая мгновенная нагрузка на БД, но возможна временная несогласованность между кешем и БД.

## Сценарии нагрузки

Для каждой стратегии выполнены три одинаковых сценария:

- `read-heavy`: 80% read / 20% write;
- `balanced`: 50% read / 50% write;
- `write-heavy`: 20% read / 80% write.

## Измеряемые метрики

- `throughput` (`req/sec`);
- средняя задержка (`avg latency`);
- количество обращений в БД на чтение (`db_hits`);
- `cache hit rate`;
- количество фактических записей в БД (`db_writes`) — особенно важно для анализа `Write-Back`.

## Таблица результатов

| Стратегия | Сценарий | Throughput (req/s) | Средняя задержка (ms) | Обращения в БД (чтение) | Hit rate кеша | DB writes |
|---|---:|---:|---:|---:|---:|---:|
| lazy | balanced | 375.14 | 1.74 | 94 | 62.99% | 246 |
| write-back | balanced | 150.09 | 0.68 | 51 | 79.35% | 90 |
| write-through | balanced | 495.05 | 2.17 | 40 | 83.74% | 254 |
| lazy | read-heavy | 458.20 | 1.34 | 100 | 74.75% | 104 |
| write-back | read-heavy | 139.61 | 0.69 | 85 | 78.37% | 81 |
| write-through | read-heavy | 453.97 | 1.12 | 81 | 79.95% | 96 |
| lazy | write-heavy | 329.01 | 2.29 | 70 | 36.36% | 390 |
| write-back | write-heavy | 131.81 | 1.09 | 19 | 82.73% | 96 |
| write-through | write-heavy | 418.27 | 2.77 | 21 | 79.21% | 399 |

## Детальный разбор результатов

### Read-heavy (80/20)

- По пропускной способности лидирует `lazy` (458.20 req/s), очень близко `write-through` (453.97 req/s).
- `write-through` показывает лучший hit rate (79.95% против 74.75% у `lazy`) и меньше DB reads.
- `write-back` имеет низкий throughput (139.61 req/s), хотя средняя задержка запроса низкая (0.69 ms).

Вывод по сценарию: для read-heavy практически паритет между `lazy` и `write-through` по throughput, но `write-through` лучше по давлению на БД.

### Balanced (50/50)

- Явный лидер `write-through` (495.05 req/s).
- У него же лучший hit rate (83.74%) и минимальные DB reads (40).
- `lazy` заметно уступает по hit rate (62.99%), потому что записи не прогревают кеш.
- `write-back` показывает самые низкие DB writes (90), что подтверждает эффект отложенной записи.

Вывод по сценарию: для смешанной нагрузки наиболее сбалансированно работает `write-through`.

### Write-heavy (20/80)

- Лидер по throughput — `write-through` (418.27 req/s).
- `lazy` заметно проседает по hit rate (36.36%) и чаще идет в БД на чтение.
- `write-back` дает наименьшее число DB writes (96 против ~390–399 у остальных), то есть сильно разгружает БД на записи в коротком окне.

Вывод по сценарию: если важна консистентность и высокая пропускная способность прямо сейчас — `write-through`; если критично снизить пиковую запись в БД — `write-back`.

## Сравнение по метрикам (агрегированно)

- **Throughput:** чаще выигрывает `write-through` (2 из 3 сценариев), `lazy` выигрывает только read-heavy.
- **Средняя задержка запроса:** минимальные значения у `write-back`, что ожидаемо из-за локальной записи в кеш.
- **Обращения в БД на чтение:** лучшие значения у `write-through`/`write-back`, `lazy` хуже при росте доли записи.
- **Hit rate кеша:** стабильно выше у `write-through` и `write-back`, ниже у `lazy` в balanced/write-heavy.
- **DB writes:** у `write-back` существенно ниже в момент нагрузки, что подтверждает отложенную запись.

## Проверка логичности результатов

Результаты выглядят логично и согласуются с теорией:

- Низкий `db_writes` у `write-back` подтверждает буферизацию записей.
- Более высокий `cache hit rate` у `write-through` объясняется обновлением кеша при каждой записи.
- Просадка `lazy` по hit rate в write-heavy ожидаема из-за отсутствия write-path в кеш.
- Различие между latency и throughput (особенно у `write-back`) допустимо: метрики показывают разные аспекты поведения системы.

## Практические рекомендации

- Если система преимущественно **читает** и допустим простой подход — можно использовать `lazy`.
- Если нужна **универсальность и стабильность** под mixed/write-heavy — `write-through` наиболее предсказуем.
- Если приоритет — **разгрузка БД на запись** и допустима eventual consistency — `write-back`.

## Ограничения эксперимента

- Один объем данных (100 ключей) и фиксированный размер нагрузки (500 запросов на прогон).
- Тестировался один flush-интервал для `write-back`.
- Нет отказных сценариев (например, падение БД в момент накопленного буфера).

Для production-оценки стоит добавить несколько размеров датасета, длительный прогон и анализ устойчивости при сбоях.

## Логи прогонов

Ниже фрагменты консольных логов (выполнено через `docker compose run --rm load-generator`):

```text
[DONE] strategy=lazy, scenario=balanced, throughput=375.14 req/s, avg_latency=1.74 ms, db_hits=94, cache_hit_rate=62.99%, db_writes=246
[DONE] strategy=write-back, scenario=balanced, throughput=150.09 req/s, avg_latency=0.68 ms, db_hits=51, cache_hit_rate=79.35%, db_writes=90
[DONE] strategy=write-through, scenario=balanced, throughput=495.05 req/s, avg_latency=2.17 ms, db_hits=40, cache_hit_rate=83.74%, db_writes=254
[DONE] strategy=lazy, scenario=read-heavy, throughput=458.20 req/s, avg_latency=1.34 ms, db_hits=100, cache_hit_rate=74.75%, db_writes=104
[DONE] strategy=write-back, scenario=read-heavy, throughput=139.61 req/s, avg_latency=0.69 ms, db_hits=85, cache_hit_rate=78.37%, db_writes=81
[DONE] strategy=write-through, scenario=read-heavy, throughput=453.97 req/s, avg_latency=1.12 ms, db_hits=81, cache_hit_rate=79.95%, db_writes=96
[DONE] strategy=lazy, scenario=write-heavy, throughput=329.01 req/s, avg_latency=2.29 ms, db_hits=70, cache_hit_rate=36.36%, db_writes=390
[DONE] strategy=write-back, scenario=write-heavy, throughput=131.81 req/s, avg_latency=1.09 ms, db_hits=19, cache_hit_rate=82.73%, db_writes=96
[DONE] strategy=write-through, scenario=write-heavy, throughput=418.27 req/s, avg_latency=2.77 ms, db_hits=21, cache_hit_rate=79.21%, db_writes=399
```
