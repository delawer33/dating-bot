# RabbitMQ vs Redis Streams — Benchmark Testbed

Automated benchmark comparing RabbitMQ and Redis Streams as message brokers.
Measures throughput, latency (avg/p95/max), and message loss across a configurable
experiment matrix.

## Quick Start

```bash
# 1. Start brokers + services (first run builds the images)
docker compose up --build -d

# 2. Wait for all healthchecks to pass (~30s)
docker compose ps

# 3. Install runner dependencies
cd runner
pip install -r requirements.txt

# 4. Run the full benchmark matrix (default: 48 runs × 60s each ≈ ~60 min)
python runner.py

# 4b. Full 48-run matrix in well under 1 hour (steady metrics, shorter runs)
python runner.py --duration 22 --drain 2 --warmup 3

# 5. Generate charts and report
python report.py

# Open results/report.md
```

## Short Smoke Test (5 runs, 10s each)

```bash
python runner.py --duration 10 --rates 1000,5000 --sizes 128,1024 --brokers rmq
```

## Experiment Matrix

| Dimension | Default values |
|-----------|---------------|
| Brokers | `rmq`, `redis_streams` |
| Configs | `durable_ack`, `inmemory_noack` |
| Message sizes | 128 B, 1 KB, 10 KB, 100 KB |
| Target rates | 1 000, 5 000, 10 000 msg/s |
| Duration | 60 s (configurable) |

**`durable_ack`** — RabbitMQ: durable queue + confirms + ack; Redis: AOF + XACK.
Tests real-world reliability. RabbitMQ's home turf.

**`inmemory_noack`** — Both brokers run fully in-memory with no ack overhead.
Tests raw speed. Redis's home turf.

## Project Structure

```
.
├── docker-compose.yml
├── producer/           FastAPI service — sends messages at a controlled rate
│   ├── main.py
│   ├── rmq_producer.py
│   ├── redis_producer.py
│   ├── rate_limiter.py
│   └── models.py
├── consumer/           FastAPI service — receives, acks, tracks latency + loss
│   ├── main.py
│   ├── rmq_consumer.py
│   ├── redis_consumer.py
│   ├── metrics_store.py
│   └── models.py
├── runner/
│   ├── runner.py       Orchestrates the full experiment matrix, writes CSV
│   ├── report.py       Reads CSV, generates 5 PNG charts + report.md
│   └── requirements.txt
├── results/
│   ├── results.csv     Raw data (appended on every run; delete for a clean header after schema changes)
│   ├── charts/         PNG charts (overwritten on report regeneration)
│   └── report.md       Final report with summary table
└── docs/
    └── decisions.md    Detailed rationale for every design choice
```

## Runner CLI Reference

```
python runner.py [options]

  --duration INT    Seconds per run              (default: 60)
  --drain INT       Drain grace after stop        (default: 5)
  --rates STR       Comma-separated msg/s targets (default: 1000,5000,10000)
  --sizes STR       Comma-separated byte sizes    (default: 128,1024,10240,102400)
  --brokers STR     Which brokers to test         (default: rmq,redis_streams)
  --configs STR     Which configs to test         (default: durable_ack,inmemory_noack)
  --output FILE     CSV output path               (default: ../results/results.csv)
  --warmup INT      Steady-state warmup (s after first msg; default 3, use 0 off)
  --dry-run         Print matrix without running
```

## Service Endpoints

| Service | URL | Endpoints |
|---------|-----|-----------|
| Producer | http://localhost:8001 | POST /start, POST /stop, POST /flush, GET /status |
| Consumer | http://localhost:8002 | POST /start, POST /stop, GET /metrics, GET /status |
| RabbitMQ management | http://localhost:15672 | guest / guest |

## What Gets Measured

- **messages/s** — steady-state throughput: messages received **after** the warmup window, divided by wall time after warmup (see `--warmup`)
- **latency avg / p95 / max** — consumer-side, from embedded `send_ts`, **warmup samples excluded**
- **`recv_count`** — all delivered messages; **`recv_steady`** — counted after warmup (CSV)
- **lost messages** — detected via `seq` number gaps
- **ack count** — messages explicitly acknowledged (relevant in `durable_ack` mode)
- **error count** — parse errors, broker errors

## Design Details

See [docs/decisions.md](docs/decisions.md) for full rationale covering:
- Why Redis Streams over Pub/Sub / List
- Token-bucket rate limiter design
- Latency measurement methodology
- Loss detection algorithm
- Resource cap choices
- Known limitations