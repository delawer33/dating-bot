# Apache JMeter — API benchmarks

This folder exercises the FastAPI surface the Telegram bot uses: **`POST /discovery/next`**, **`POST /profile/me`**, **`POST /discovery/incoming-likes`**, plus a **`GET /health`** sanity check in a setUp thread group. Every mutating route is behind **`X-Bot-Secret`**, matching production.

## Prerequisites

1. Stack running with API reachable from where JMeter runs (for example `docker compose up` and API on port **8000**).
2. **`BOT_SECRET`** identical to the API container (`backend/.env` / compose).
3. **Seeded users** for every `telegram_id` in the CSV (same numeric range as the default seed).

Seed the database (from repo root):

```bash
docker compose exec api python scripts/seed_benchmark_discovery_users.py --count 400 --write-viewers-csv /tmp/viewers.csv
docker compose cp api:/tmp/viewers.csv benchmarks/jmeter/viewers.csv
```

Or from `backend/` with `DATABASE_URL` pointing at Postgres:

```bash
cd backend
python scripts/seed_benchmark_discovery_users.py --count 400 --write-viewers-csv ../benchmarks/jmeter/viewers.csv
```

The default first id is **9100000000001**; the committed `viewers.csv` lists the first ten ids in that range.

## Run (Docker)

Use any JMeter image you prefer (`alpine/jmeter`, `justb4/jmeter`, or your own). Override with **`JMETER_IMAGE`**.

```bash
export BOT_SECRET='change-me-in-production'   # same as API
export HOST=localhost                         # or api when running inside compose network
export PORT=8000
./benchmarks/jmeter/run-benchmark.sh
```

Tune load with environment variables (optional):

| Variable   | Default | Meaning                          |
|-----------|---------|----------------------------------|
| `THREADS` | 30      | Concurrent virtual users         |
| `RAMPUP`  | 120     | Seconds to start all threads     |
| `DURATION`| 300     | Test duration (seconds)          |
| `CSV`     | viewers.csv | Path under `benchmarks/jmeter` |

## Run (one-liner)

```bash
docker run --rm -v "$(pwd)/benchmarks/jmeter:/t" -w /t alpine/jmeter:latest \
  -n -t dating-api-benchmark.jmx \
  -JBOT_SECRET="$BOT_SECRET" -JHOST=localhost -JPORT=8000 \
  -Jthreads=50 -Jrampup=60 -Jduration=180 \
  -l results/run.jtl -e -o results/html-report
```

JMeter writes **`results/`** (gitignored). Create it first if you pass literal paths as above.

## JMeter `-J` properties

| Property   | Default     | Description                    |
|-----------|-------------|--------------------------------|
| `HOST`    | localhost   | API hostname                   |
| `PORT`    | 8000        | API port                       |
| `PROTOCOL`| http        | http or https                  |
| `BOT_SECRET` | _(empty)_ | Required for authenticated samplers |
| `threads` | 20          | Load thread count              |
| `rampup`  | 60          | Ramp-up (seconds)              |
| `duration`| 300         | Scheduler duration (seconds)   |
| `delay`   | 0           | Startup delay (seconds)        |
| `csv`     | viewers.csv | Viewer pool CSV (under `/t`)   |
| `think_deviation` | 150 | Gaussian timer offset (ms)     |
| `think_range`     | 400 | Gaussian timer range (ms)    |

## Correlating with observability

With the **`observability`** profile (Prometheus + Grafana), HTTP metrics are labeled by **route name**. Run a load test, then inspect latency and saturation on the API dashboard and Postgres pool metrics (`STAGE_4.md`).

## Files

| File | Role |
|------|------|
| `dating-api-benchmark.jmx` | Main test plan |
| `viewers.csv` | `telegram_id` column (replace after large seeds) |
| `run-benchmark.sh` | Docker wrapper + HTML report |
