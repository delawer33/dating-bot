# JMeter API benchmark (realistic mix)

The plan runs **two thread groups in parallel**:

1. **01 Health probes** — `GET /health` (no bot secret; cheap liveness under load).
2. **02 Realistic bot session** — per iteration, one **Transaction** `session` that mirrors bot→API traffic:
   - `POST /profile/me` (card + presign path)
   - `POST /discovery/incoming-likes` (`mode=inbox`, `limit=10`)
   - `POST /discovery/next`
   - If the response includes a profile card, **regex** extracts `target_user_id`, then Groovy picks **like** vs **skip** (Bernoulli, default **22%** like).
   - `POST /discovery/like` or `POST /discovery/skip` with the extracted UUID  
   - Write responses assert **HTTP 200 or 409** (409 = duplicate interaction under concurrency, treated as acceptable for this load model).

**Think times** use `UniformRandomTimer` between steps (tunable, see table below).

The machine-readable plan is generated from **`generate_jmx.py`** so the XML stays maintainable. After editing the generator, run:

```bash
python3 benchmarks/jmeter/generate_jmx.py
```

Commit the updated `dating-api-benchmark.jmx` when the generator changes.

## Prerequisites

- Stack up (`docker compose up …`) with **API** and **Postgres** (and Redis/RabbitMQ/MinIO as in compose).
- Registered users for every `telegram_id` in `viewers.csv` (see seeding).
- **`BOT_SECRET`** passed to JMeter as **`-Jbot.secret=...`** must match the API.
- Prefer the **`dating-jmeter`** image (JMeter 5.6.3); many distro packages ship an unusably old CLI.

## Seed Postgres

Default dataset: **400** telegram ids starting at **9100000000001**. Seed is idempotent.

**Inside the API container** (cannot write `viewers.csv` to the host from here):

```bash
docker compose exec api python scripts/seed_benchmark_discovery_users.py --count 400
```

**From the host** (also refresh `viewers.csv` next to this README):

```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://dating:dating@localhost:5432/dating
python scripts/seed_benchmark_discovery_users.py --count 400 \
  --write-viewers-csv ../benchmarks/jmeter/viewers.csv
```

## Run with Docker (recommended): Compose network

Attach JMeter to the **same Docker network** as the stack and call the API by **service name** (`api:8000`). This avoids `host.docker.internal` / firewall issues.

From the **repository root** (pick your own `BOT_SECRET` or interpolate from the running API):

```bash
docker build -t dating-jmeter -f benchmarks/jmeter/Dockerfile benchmarks/jmeter

mkdir -p benchmarks/jmeter/results

BOT_SECRET=$(docker compose exec -T api python -c "import os; print(os.environ.get('BOT_SECRET',''))")

# If a previous run left root-owned files under results/, clear them:
docker run --rm -v "$PWD/benchmarks/jmeter:/bench" alpine:3.20 sh -c "rm -rf /bench/results/html-report /bench/results/run.jtl"

docker run --rm --network dating-bot_default \
  -v "$PWD/benchmarks/jmeter:/bench" -w /bench \
  dating-jmeter \
  -f -n -t dating-api-benchmark.jmx \
  -l results/run.jtl \
  -e -o results/html-report \
  -Japi.host=api \
  -Japi.port=8000 \
  -Jbot.secret="$BOT_SECRET" \
  -JlikeRatio=0.22
```

Open **`benchmarks/jmeter/results/html-report/index.html`** after a run.

### Host-only API (no compose network)

If the API is published on the host (`localhost:8000`), use **`--add-host=host.docker.internal:host-gateway`** (Linux) and **`-Japi.host=host.docker.internal`**, or point **`-Japi.host=`** at a reachable IP.

## Run with a local JMeter 5.6+ install

```bash
cd benchmarks/jmeter
python3 generate_jmx.py
mkdir -p results
jmeter -f -n -t dating-api-benchmark.jmx \
  -l results/run.jtl -e -o results/html-report \
  -Japi.host=127.0.0.1 -Japi.port=8000 -Jbot.secret=change-me-in-production
```

## Tunables (JMeter `-J` properties)

| Property | Default | Meaning |
|----------|---------|---------|
| `api.host` | `localhost` | HTTP host |
| `api.port` | `8000` | HTTP port |
| `api.protocol` | `http` | `http` or `https` |
| `bot.secret` | `change-me-in-production` | `X-Bot-Secret` |
| `csv.file` | `viewers.csv` | CSV path (relative to **`-w` / cwd** of JMeter) |
| `likeRatio` | `0.22` | Probability of **like** after a successful **next** (remainder → **skip**) |
| `health.users` | `4` | Threads for `/health` |
| `health.ramp` | `4` | Ramp-up (s) |
| `health.loops` | `40` | Loops per health thread |
| `journey.users` | `35` | Threads for the realistic session |
| `journey.ramp` | `25` | Ramp-up (s) |
| `journey.loops` | `12` | Loops per journey thread (each loop = full transaction) |
| `think.ms.min` | `15` | Uniform timer base (ms) before profile / inbox / next |
| `think.ms.range` | `120` | Added random range (ms) for those timers |
| `think.action.min` | `25` | Base (ms) before like/skip |
| `think.action.range` | `220` | Random range (ms) before like/skip |

Example heavier run: `-Jjourney.users=60 -Jjourney.loops=25 -JlikeRatio=0.15`.

## Interpreting results

- Use the HTML dashboard for **throughput**, **p95/p99**, and **errors**. Compare runs only when data volume, compose profile, and `-J` tuning match except for the variable you are testing.
- Correlate with **`GET /metrics`** (`STAGE_4.md`): HTTP histograms, `discovery_actions_total`, DB pool gauges, Rabbit publish counters.

## Files

| File | Role |
|------|------|
| `generate_jmx.py` | Emits `dating-api-benchmark.jmx` |
| `dating-api-benchmark.jmx` | Generated test plan (commit when generator changes) |
| `viewers.csv` | `telegram_id` column; keep in sync with seed range/count |
| `Dockerfile` | JMeter 5.6.3 CLI image |
| `results/` | `.jtl` + HTML report (gitignored; may be root-owned if not cleaned with a small helper container) |
