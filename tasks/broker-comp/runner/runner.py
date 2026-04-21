#!/usr/bin/env python3
"""
Benchmark runner — orchestrates the full experiment matrix.

Usage:
    python runner.py [options]

Options:
    --duration INT      Seconds per run (default: 60)
    --drain INT         Drain grace period after producer stops (default: 5)
    --rates STR         Comma-separated target rates, msg/sec (default: 1000,5000,10000)
    --sizes STR         Comma-separated message sizes, bytes (default: 128,1024,10240,102400)
    --brokers STR       Comma-separated brokers: rmq,redis_streams (default: both)
    --configs STR       Comma-separated configs: durable_ack,inmemory_noack (default: both)
    --output FILE       CSV output file (default: ../results/results.csv)
    --producer-url URL  Producer service URL (default: http://localhost:8001)
    --consumer-url URL  Consumer service URL (default: http://localhost:8002)
    --warmup INT        Seconds after first received message to exclude from
                        steady throughput and latency stats (default: 3; use 0 to disable)
    --dry-run           Print the experiment matrix without running
"""

import argparse
import csv
import itertools
import os
import sys
import time
from pathlib import Path

import httpx

PRODUCER_URL = os.getenv("PRODUCER_URL", "http://localhost:8001")
CONSUMER_URL = os.getenv("CONSUMER_URL", "http://localhost:8002")
DEFAULT_OUTPUT = Path(__file__).parent.parent / "results" / "results.csv"

CSV_FIELDS = [
    "broker", "config", "msg_size", "target_rate", "duration", "warmup_seconds",
    "sent_count", "recv_count", "recv_steady", "ack_count", "lost_count", "error_count",
    "throughput_msg_s", "latency_avg_ms", "latency_p95_ms", "latency_max_ms",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RMQ vs Redis benchmark runner")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--drain", type=int, default=5)
    parser.add_argument("--rates", type=str, default="1000,5000,10000")
    parser.add_argument("--sizes", type=str, default="128,1024,10240,102400")
    parser.add_argument("--brokers", type=str, default="rmq,redis_streams")
    parser.add_argument("--configs", type=str, default="durable_ack,inmemory_noack")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument("--producer-url", type=str, default=PRODUCER_URL)
    parser.add_argument("--consumer-url", type=str, default=CONSUMER_URL)
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="Steady-state warmup (seconds after first msg); 0 disables",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.warmup > 0 and args.warmup >= args.duration:
        parser.error("--warmup must be less than --duration (or use --warmup 0)")
    return args


def build_matrix(args: argparse.Namespace) -> list[dict]:
    brokers = [b.strip() for b in args.brokers.split(",")]
    configs = [c.strip() for c in args.configs.split(",")]
    rates = [int(r.strip()) for r in args.rates.split(",")]
    sizes = [int(s.strip()) for s in args.sizes.split(",")]

    matrix = []
    for broker, config, size, rate in itertools.product(brokers, configs, sizes, rates):
        matrix.append({
            "broker": broker,
            "config": config,
            "msg_size": size,
            "target_rate": rate,
            "duration": args.duration,
            "warmup_seconds": args.warmup,
        })
    return matrix


def flush_broker(client: httpx.Client, producer_url: str, broker: str) -> None:
    resp = client.post(f"{producer_url}/flush", params={"broker": broker}, timeout=10)
    if resp.is_error:
        msg = resp.text[:500]
        try:
            payload = resp.json()
            if isinstance(payload, dict) and "detail" in payload:
                msg = str(payload["detail"])
        except Exception:
            pass
        print(f"  flush HTTP {resp.status_code}: {msg}", flush=True)
    resp.raise_for_status()


def start_consumer(client: httpx.Client, consumer_url: str, run: dict) -> None:
    # Consumer /start awaits broker prepare (RMQ declare, Redis PING/XGROUP) before 202.
    resp = client.post(f"{consumer_url}/start", json=run, timeout=30)
    if resp.is_error:
        print(f"  consumer /start HTTP {resp.status_code}: {resp.text[:500]}", flush=True)
    resp.raise_for_status()


def start_producer(client: httpx.Client, producer_url: str, run: dict) -> None:
    resp = client.post(f"{producer_url}/start", json=run, timeout=10)
    resp.raise_for_status()


def stop_producer(client: httpx.Client, producer_url: str) -> int:
    resp = client.post(f"{producer_url}/stop", timeout=10)
    resp.raise_for_status()
    return resp.json().get("sent_count", 0)


def stop_consumer(client: httpx.Client, consumer_url: str, sent_count: int) -> None:
    resp = client.post(f"{consumer_url}/stop", params={"sent_count": sent_count}, timeout=15)
    resp.raise_for_status()


def get_metrics(client: httpx.Client, consumer_url: str) -> dict:
    resp = client.get(f"{consumer_url}/metrics", timeout=10)
    resp.raise_for_status()
    return resp.json()


def run_experiment(client: httpx.Client, args: argparse.Namespace, run: dict) -> dict | None:
    broker = run["broker"]
    config = run["config"]
    size = run["msg_size"]
    rate = run["target_rate"]
    duration = run["duration"]

    label = f"[{broker:15s}] [{config:15s}] size={size:>7}B  rate={rate:>6}/s  dur={duration}s"
    print(f"  Starting  {label}", flush=True)

    try:
        # Ensure producer task is finished so /flush is not rejected with 409.
        try:
            client.post(f"{args.producer_url}/stop", timeout=10)
        except Exception:
            pass
        flush_broker(client, args.producer_url, broker)
        start_consumer(client, args.consumer_url, run)
        time.sleep(0.05)
        start_producer(client, args.producer_url, run)

        time.sleep(duration)

        sent_count = stop_producer(client, args.producer_url)
        time.sleep(args.drain)
        stop_consumer(client, args.consumer_url, sent_count)

        metrics = get_metrics(client, args.consumer_url)
        tput = metrics.get("throughput_msg_s", 0)
        p95 = metrics.get("latency_p95_ms", 0)
        lost = metrics.get("lost_count", 0)
        print(
            f"  Done      {label}  "
            f"tput={tput:>8.0f}/s  p95={p95:>8.2f}ms  lost={lost}",
            flush=True,
        )
        return metrics

    except Exception as exc:
        print(f"  ERROR     {label}  -> {exc}", flush=True)
        return None


def write_csv_row(writer: csv.DictWriter, metrics: dict) -> None:
    row = {field: metrics.get(field, "") for field in CSV_FIELDS}
    writer.writerow(row)


def main() -> None:
    args = parse_args()
    matrix = build_matrix(args)
    total = len(matrix)

    print(f"\nBenchmark matrix: {total} runs")
    print(f"  Duration per run : {args.duration}s")
    print(f"  Drain grace      : {args.drain}s")
    print(f"  Output           : {args.output}")
    print(f"  Est. total time  : ~{total * (args.duration + args.drain + 3) // 60} min\n")

    if args.dry_run:
        for i, run in enumerate(matrix, 1):
            print(f"  {i:3d}. {run}")
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = output_path.exists()

    with (
        httpx.Client() as client,
        open(output_path, "a", newline="") as f,
    ):
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()

        for i, run in enumerate(matrix, 1):
            print(f"\nRun {i}/{total}", flush=True)
            metrics = run_experiment(client, args, run)
            if metrics:
                write_csv_row(writer, metrics)
                f.flush()

    print(f"\nDone. Results written to {args.output}")


if __name__ == "__main__":
    main()
