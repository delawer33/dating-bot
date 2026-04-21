# Architecture & Design Decisions

This document records every significant design choice made in this benchmark testbed,
explains the reasoning behind it, and flags the trade-offs and known limitations.

---

## 1. Why Redis Streams instead of Pub/Sub or List

Redis offers three messaging primitives. The choice matters because it directly affects
what the benchmark is actually comparing.

| Primitive | Persistence | Consumer ack | Consumer groups | Ordering |
|-----------|-------------|--------------|-----------------|---------|
| **Streams** | yes (AOF/RDB) | yes (XACK) | yes (XGROUP) | per-stream |
| List (BRPOP) | yes | no | no (BLPOP races) | FIFO |
| Pub/Sub | no | no | no | irrelevant |

**Redis Pub/Sub** drops all messages if no subscriber is connected at publish time.
This makes a fair comparison with RabbitMQ impossible — RMQ never loses a message
from a durable queue just because the consumer is momentarily offline.

**Redis List** is the traditional queue pattern and works well, but has no
acknowledgement — if the consumer crashes after BRPOP, the message is gone.
This makes `durable_ack` semantics impossible to implement.

**Redis Streams** (introduced in Redis 5.0) is the only primitive that supports:
- persistent storage (survives broker restart when AOF is on)
- consumer groups (competing consumers with ownership tracking)
- `XACK` — explicit per-message acknowledgement

It is therefore the only Redis primitive that can be tested in both `durable_ack`
and `inmemory_noack` modes using the same code path, which is required by the
experiment design.

---

## 2. The Two Experiment Configs: `durable_ack` vs `inmemory_noack`

Rather than forcing both brokers into a single configuration, the testbed runs
each broker in two modes. This captures both the "fair fight" angle and the
"native strengths" angle within a single matrix.

### `durable_ack` — reliability / RabbitMQ home turf

- **RabbitMQ**: durable queue, `delivery_mode=PERSISTENT`, publisher confirms enabled,
  consumer sends explicit `ack`
- **Redis Streams**: `appendonly yes` set via `CONFIG SET` before the run,
  `XREADGROUP` + `XACK` used for consuming

Both brokers guarantee that a message survives a broker crash and is redelivered
after consumer failure. This is the config where RabbitMQ has been optimized for
years. Comparing here reveals RMQ's advantage in mature reliability guarantees.

### `inmemory_noack` — speed / Redis home turf

- **RabbitMQ**: transient queue (auto-delete), no publisher confirms, no consumer ack
- **Redis Streams**: `appendonly no`, plain `XREAD` (no consumer group, no XACK)

Both brokers run at maximum speed with no durability overhead. This is the config
where Redis is expected to shine — it was designed as an in-memory data structure
server first. Comparing here reveals Redis's raw throughput advantage.

**Why this framing matters**: Comparing only in `durable_ack` mode would make Redis
look unfair (it's adding AOF overhead it doesn't normally need). Comparing only
in `inmemory_noack` mode would make RabbitMQ look unfair (it's stripping out the
reliability it was designed for). Showing both gives a complete picture.

---

## 3. Resource Caps: 2 CPU / 1 GB RAM

Docker Compose `deploy.resources.limits` enforce hard ceilings on both brokers.

**Why cap at all**: Without limits, results depend entirely on the host machine.
A developer machine running other processes will produce wildly different numbers
on different days. Hard caps make results reproducible and portable.

**Why 2 CPU / 1 GB**: These are realistic production-tier limits for a single
broker instance on a shared cloud VM (e.g., AWS t3.medium has 2 vCPU / 4 GB,
with 1 GB leaving room for OS overhead). Going lower (1 CPU) would create
artificial bottlenecks unrepresentative of any real deployment.

**Known limitation**: Docker's CPU limiting is implemented via CFS bandwidth
throttling, not affinity. At very high rates, scheduling jitter may add latency
noise that wouldn't exist on a dedicated core. This affects both brokers equally.

---

## 4. Latency Measurement: Embedded `send_ts`, Monotonic Clock

Each message carries a `send_ts` field set with `time.monotonic()` on the producer.
The consumer reads it upon receipt and computes `latency_ms = (time.monotonic() - send_ts) * 1000`.

**Why embedded timestamp over external clock sync**: Synchronizing two clocks
across Docker containers introduces NTP/PTP jitter (typically 0.1–1 ms on a local
machine, up to 10 ms over a network). For latencies that may be in the single-digit
millisecond range, this would corrupt the measurements. Using the same process's
monotonic clock — by sending the `send_ts` inside the message — means the only
latency measured is the actual broker transit time.

**Why `time.monotonic()` over `time.time()`**: Monotonic clocks never jump backwards
(no NTP adjustments mid-run). This prevents negative latency samples and
incorrect averages.

**Limitation**: Producer and consumer are in separate processes, so `time.monotonic()`
values are not directly comparable. To work around this, the runner starts the
consumer first and the producer second. The consumer's monotonic clock is initialized
at `MetricsStore` creation, and latency is computed as relative difference from the
embedded value. In practice, on the same host, monotonic clocks share the same
origin (the system boot time) across processes, so this is valid. This would break
if producer and consumer were on separate hosts.

---

## 5. Rate Control: Token-Bucket Limiter

The producer uses a token-bucket algorithm (`rate_limiter.py`) rather than
`asyncio.sleep(1/rate)`.

**Why not sleep-based pacing**: A sleep-based approach accumulates drift. If
publishing a batch of messages takes 10 ms, sleeping `1/rate` seconds after each
one results in a rate lower than the target. At 10,000 msg/s, even 0.1 ms of
extra processing per message translates to 1,000 msg/s of drift.

**How token bucket works**: The bucket refills at exactly `rate` tokens/second.
Each publish call acquires one token. If a token is available, the call returns
immediately. If not, it calculates the precise wait time to the next token and
sleeps for exactly that duration. This self-corrects: if publishing was slow in
one interval, the next interval compensates by firing immediately until the
deficit is recovered.

---

## 6. Loss Detection: Sequence Number Gaps

Each message carries a monotonically increasing `seq` integer. The consumer
tracks all received `seq` values in a set. After the run:

```python
max_seq = max(seq_seen)
expected = max_seq + 1          # 0 .. max_seq inclusive
lost = expected - len(seq_seen) # set cardinality = unique seq received
```

This detects both dropped messages and duplicates (duplicates are silently
deduplicated by the set). It does not distinguish between "producer never sent it"
and "broker lost it in transit" — to distinguish these, the runner compares
`sent_count` (from the producer) against `recv_count` (from the consumer).

**Edge case**: If the producer sends `[0, 1, 3, 4]` (skips 2), the algorithm
reports 1 lost. If the producer itself crashed at `seq=1`, the comparison
`sent_count=2` vs `recv_count=2` would reveal no loss at the broker level.

---

## 7. Why 1 Producer : 1 Consumer for the Baseline

Multiple producers add write contention at the broker. Multiple consumers add
scheduling and coordination overhead. Either makes it harder to attribute
performance differences to the broker itself versus the client parallelism strategy.

Starting with 1:1 isolates the broker's single-connection throughput limit. This
is the fair starting point for comparison. Scaling experiments (N:1, 1:N) can be
added as additional flags to the runner without changing the existing results.

---

## 8. Why the Producer and Runner Are Separate Processes

The runner is a plain Python script running locally (not in Docker). The producer
and consumer are FastAPI services inside Docker.

**Benefits**:
- The runner can time the experiment wall-clock independently of Docker
- The runner can flush and reset broker state between runs via HTTP
- Runner failures do not crash the producer/consumer (they can be restarted)
- A future web UI could replace the runner CLI without changing the services

**Trade-off**: The HTTP round-trips for `/start`, `/stop`, and `/metrics` add
~1–5 ms of control-plane latency. This does not affect measurement accuracy
because these calls only happen at run boundaries, not per message.

---

## 9. AOF Toggle via `CONFIG SET`

The Redis producer calls `CONFIG SET appendonly yes/no` at the start of each run
to switch between `durable_ack` and `inmemory_noack` modes without restarting the
Redis container.

**Important**: Redis must be started without `--save ""` disabled for CONFIG SET
to work in some configurations. The docker-compose.yml starts Redis with
`appendonly no` as the default but does not protect with `--protected-mode`.
`CONFIG SET` requires that `protected-mode` is off or the command is issued from
localhost — both are true in the Docker network context.

**Limitation**: There is a brief window between `CONFIG SET appendonly yes` and the
first message where the AOF may not have flushed the prior run's data. This is
acceptable for a benchmark where the goal is steady-state throughput, not
point-in-time durability proof.

---

## 10. Known Limitations and Caveats

1. **Monotonic clock scope**: Latency is only meaningful when producer and consumer
   run on the same physical host. On different hosts, clock synchronization error
   would dominate.

2. **Single-queue topology**: RabbitMQ topic exchanges, dead-letter queues, and
   header routing are not tested. These features add overhead but are not part
   of this baseline comparison.

3. **No TLS**: Both connections are unencrypted. In production, TLS adds latency
   (typically 0.1–0.5 ms/message for 1KB payloads). This affects both brokers
   roughly equally.

4. **Consumer prefetch**: The RabbitMQ consumer uses `prefetch_count=100`. Higher
   values improve throughput at the cost of in-flight message count. Lower values
   reduce throughput. The value 100 is a common production default.

5. **Payload is compressible zeros**: The benchmark payload is `bytes(msg_size)`
   (all zeros), which compresses extremely well. Real payloads (JSON, Protobuf,
   random bytes) would produce different memory and network utilization. This is
   acceptable because both brokers receive the same payload.

6. **Docker overhead**: Running broker and services on the same machine means
   CPU contention is possible. The broker containers are capped but the
   producer/consumer are not. In a production environment, brokers run on
   dedicated hardware.

7. **RabbitMQ queue names per config**: A queue cannot be redeclared with different
   arguments under the same name. After `durable_ack` creates a durable queue,
   switching to `inmemory_noack` with `durable=False` on the same name triggers
   `PRECONDITION_FAILED` and the producer sends nothing. The implementation uses
   two physical queue names (`benchmark_queue_durable_ack` and
   `benchmark_queue_inmemory_noack`) and deletes both on flush. The transient
   queue uses `auto_delete=False` so a producer that connects milliseconds before
   the consumer has finished declaring does not hit `auto_delete` edge cases; the
   The consumer service additionally runs `prepare_queue()` (awaited inside
   `POST /start`) so the queue is declared on the broker before the HTTP response
   returns; the runner still waits a few milliseconds before starting the producer.

8. **Warmup window**: After the **first received message**, the next `warmup_seconds`
   (default 3) are excluded from latency samples and from the steady-state throughput
   denominator (`recv_steady` / time after warmup). Total `recv_count` still includes
   warmup deliveries so you can compare against producer `sent_count`.

9. **Latency units (ms vs µs)**: Latency is computed in **seconds** as a float
   (`recv_ts - send_ts`) and multiplied by 1000 only for CSV/report display.
   Sub-millisecond latencies are not rounded to zero by that step. If CSV rows show
   `latency_*_ms = 0` while `recv_count = 0`, the issue is **no messages delivered**,
   not insufficient time resolution. Extra µs columns would be presentation only.

10. **Docker Redis port**: Services on the Compose network must connect to Redis on
   **container port 6379**. Host port `6378` in `ports:` is only for access from the
   host; `redis://redis:6378` from another container is incorrect.
