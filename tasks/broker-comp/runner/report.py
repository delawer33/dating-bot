#!/usr/bin/env python3
"""
Report generator — reads results.csv and produces:
  - 5 PNG charts in results/charts/
  - results/report.md with embedded chart links and a summary table

Usage:
    python report.py [--input PATH] [--output-dir PATH]
"""

import argparse
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

import runner as _runner

matplotlib.use("Agg")

BROKER_LABELS = {"rmq": "RabbitMQ", "redis_streams": "Redis Streams"}
CONFIG_LABELS = {"durable_ack": "durable + ack", "inmemory_noack": "in-memory / no-ack"}

COLORS = {
    ("rmq", "durable_ack"): "#e07b39",
    ("rmq", "inmemory_noack"): "#f4a261",
    ("redis_streams", "durable_ack"): "#2a9d8f",
    ("redis_streams", "inmemory_noack"): "#57cc99",
}

MARKERS = {
    ("rmq", "durable_ack"): "o",
    ("rmq", "inmemory_noack"): "s",
    ("redis_streams", "durable_ack"): "^",
    ("redis_streams", "inmemory_noack"): "D",
}

DEFAULT_INPUT = Path(__file__).parent.parent / "results" / "results.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate benchmark report")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT))
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def load_data(input_path: str) -> pd.DataFrame:
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(input_path)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines:
        raise ValueError(f"Empty results file: {input_path}")
    header_tokens = lines[0].split(",")
    data_tokens = lines[1].split(",") if len(lines) > 1 else []
    n_expected = len(_runner.CSV_FIELDS)
    if "warmup_seconds" in header_tokens:
        df = pd.read_csv(path)
    elif len(data_tokens) == n_expected:
        df = pd.read_csv(path, names=_runner.CSV_FIELDS, skiprows=1, header=None)
    else:
        df = pd.read_csv(path)

    if "warmup_seconds" not in df.columns:
        df["warmup_seconds"] = 0
    df["warmup_seconds"] = pd.to_numeric(df["warmup_seconds"], errors="coerce").fillna(0)

    if "recv_steady" not in df.columns:
        df["recv_steady"] = df["recv_count"]
    df["recv_steady"] = pd.to_numeric(df["recv_steady"], errors="coerce").fillna(df["recv_count"])

    df["broker"] = df["broker"].astype(str)
    df["config"] = df["config"].astype(str)
    df["broker_label"] = df["broker"].map(BROKER_LABELS)
    df["config_label"] = df["config"].map(CONFIG_LABELS)
    df["series"] = df["broker"] + " / " + df["config_label"]
    lost = pd.to_numeric(df["lost_count"], errors="coerce").fillna(0)
    sent = pd.to_numeric(df["sent_count"], errors="coerce").fillna(0)
    df["loss_rate_pct"] = (lost / sent.replace(0, 1) * 100).round(2)
    return df


def _series_keys(df: pd.DataFrame) -> list[tuple[str, str]]:
    return sorted(df[["broker", "config"]].drop_duplicates().itertuples(index=False, name=None))


def chart_throughput_vs_size(df: pd.DataFrame, charts_dir: Path) -> Path:
    """Throughput vs message size — one panel per target rate (no averaging across rates)."""
    rates = sorted(df["target_rate"].unique())
    n = len(rates)
    fig, axes = plt.subplots(1, n, figsize=(5.2 * n, 5), squeeze=False)
    axes_flat = axes[0]

    for ax, rate in zip(axes_flat, rates, strict=True):
        for broker, config in _series_keys(df):
            sub = (
                df[(df.broker == broker) & (df.config == config) & (df.target_rate == rate)]
                .sort_values("msg_size")
            )
            label = f"{BROKER_LABELS[broker]} / {CONFIG_LABELS[config]}"
            ax.plot(
                sub["msg_size"],
                sub["throughput_msg_s"],
                marker=MARKERS[(broker, config)],
                color=COLORS[(broker, config)],
                label=label,
                linewidth=2,
            )
        ax.set_xscale("log")
        ax.set_xlabel("Message size (bytes)", fontsize=10)
        ax.set_ylabel("Throughput (msg/s)", fontsize=10)
        ax.set_title(f"Target {int(rate):,} msg/s", fontsize=11)
        ax.legend(fontsize=7, loc="best")
        ax.grid(True, alpha=0.3)

    fig.suptitle("Throughput vs Message Size (by target rate)", fontsize=13, y=1.02)
    fig.tight_layout()

    path = charts_dir / "01_throughput_vs_size.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_p95_latency_vs_size(df: pd.DataFrame, charts_dir: Path) -> Path:
    """p95 latency vs message size — one panel per target rate."""
    rates = sorted(df["target_rate"].unique())
    n = len(rates)
    fig, axes = plt.subplots(1, n, figsize=(5.2 * n, 5), squeeze=False)
    axes_flat = axes[0]

    for ax, rate in zip(axes_flat, rates, strict=True):
        for broker, config in _series_keys(df):
            sub = (
                df[(df.broker == broker) & (df.config == config) & (df.target_rate == rate)]
                .sort_values("msg_size")
            )
            label = f"{BROKER_LABELS[broker]} / {CONFIG_LABELS[config]}"
            ax.plot(
                sub["msg_size"],
                sub["latency_p95_ms"],
                marker=MARKERS[(broker, config)],
                color=COLORS[(broker, config)],
                label=label,
                linewidth=2,
            )
        ax.set_xscale("log")
        ax.set_xlabel("Message size (bytes)", fontsize=10)
        ax.set_ylabel("p95 Latency (ms)", fontsize=10)
        ax.set_title(f"Target {int(rate):,} msg/s", fontsize=11)
        ax.legend(fontsize=7, loc="best")
        ax.grid(True, alpha=0.3)

    fig.suptitle("p95 Latency vs Message Size (by target rate)", fontsize=13, y=1.02)
    fig.tight_layout()

    path = charts_dir / "02_p95_latency_vs_size.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_throughput_vs_rate(df: pd.DataFrame, charts_dir: Path) -> Path:
    """Throughput vs target rate — one panel per message size (no averaging across sizes)."""
    sizes = sorted(df["msg_size"].unique())
    n = len(sizes)
    fig, axes = plt.subplots(1, n, figsize=(4.3 * n, 5), squeeze=False)
    axes_flat = axes[0]

    for ax, size in zip(axes_flat, sizes, strict=True):
        rates = sorted(df["target_rate"].unique())
        ax.plot(rates, rates, linestyle="--", color="gray", linewidth=1, label="ideal")
        for broker, config in _series_keys(df):
            sub = (
                df[(df.broker == broker) & (df.config == config) & (df.msg_size == size)]
                .sort_values("target_rate")
            )
            label = f"{BROKER_LABELS[broker]} / {CONFIG_LABELS[config]}"
            ax.plot(
                sub["target_rate"],
                sub["throughput_msg_s"],
                marker=MARKERS[(broker, config)],
                color=COLORS[(broker, config)],
                label=label,
                linewidth=2,
            )
        ax.set_xlabel("Target rate (msg/s)", fontsize=10)
        ax.set_ylabel("Actual throughput (msg/s)", fontsize=10)
        ax.set_title(f"Payload {int(size):,} B", fontsize=11)
        ax.legend(fontsize=7, loc="best")
        ax.grid(True, alpha=0.3)

    fig.suptitle("Throughput vs Target Rate (by message size)", fontsize=13, y=1.02)
    fig.tight_layout()

    path = charts_dir / "03_throughput_vs_rate.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_p95_latency_vs_rate(df: pd.DataFrame, charts_dir: Path) -> Path:
    """p95 latency vs target rate — one panel per message size."""
    sizes = sorted(df["msg_size"].unique())
    n = len(sizes)
    fig, axes = plt.subplots(1, n, figsize=(4.3 * n, 5), squeeze=False)
    axes_flat = axes[0]

    for ax, size in zip(axes_flat, sizes, strict=True):
        for broker, config in _series_keys(df):
            sub = (
                df[(df.broker == broker) & (df.config == config) & (df.msg_size == size)]
                .sort_values("target_rate")
            )
            label = f"{BROKER_LABELS[broker]} / {CONFIG_LABELS[config]}"
            ax.plot(
                sub["target_rate"],
                sub["latency_p95_ms"],
                marker=MARKERS[(broker, config)],
                color=COLORS[(broker, config)],
                label=label,
                linewidth=2,
            )
        ax.set_xlabel("Target rate (msg/s)", fontsize=10)
        ax.set_ylabel("p95 Latency (ms)", fontsize=10)
        ax.set_title(f"Payload {int(size):,} B", fontsize=11)
        ax.legend(fontsize=7, loc="best")
        ax.grid(True, alpha=0.3)

    fig.suptitle("p95 Latency vs Target Rate (by message size)", fontsize=13, y=1.02)
    fig.tight_layout()

    path = charts_dir / "04_p95_latency_vs_rate.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_loss_rate_vs_rate(df: pd.DataFrame, charts_dir: Path) -> Path:
    """Message loss rate (%) vs target rate — one panel per message size."""
    sizes = sorted(df["msg_size"].unique())
    n = len(sizes)
    fig, axes = plt.subplots(1, n, figsize=(4.3 * n, 5), squeeze=False)
    axes_flat = axes[0]

    for ax, size in zip(axes_flat, sizes, strict=True):
        for broker, config in _series_keys(df):
            sub = (
                df[(df.broker == broker) & (df.config == config) & (df.msg_size == size)]
                .sort_values("target_rate")
            )
            label = f"{BROKER_LABELS[broker]} / {CONFIG_LABELS[config]}"
            ax.plot(
                sub["target_rate"],
                sub["loss_rate_pct"],
                marker=MARKERS[(broker, config)],
                color=COLORS[(broker, config)],
                label=label,
                linewidth=2,
            )
        ax.set_xlabel("Target rate (msg/s)", fontsize=10)
        ax.set_ylabel("Message loss rate (%)", fontsize=10)
        ax.set_title(f"Payload {int(size):,} B", fontsize=11)
        ax.legend(fontsize=7, loc="best")
        ax.grid(True, alpha=0.3)

    fig.suptitle("Message Loss Rate vs Target Rate (by message size)", fontsize=13, y=1.02)
    fig.tight_layout()

    path = charts_dir / "05_loss_rate_vs_rate.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def build_summary_table(df: pd.DataFrame) -> str:
    """Mean over message sizes only, grouped by broker + config + target rate (no rate/size cross-mix)."""
    agg = (
        df.groupby(["broker", "config", "target_rate"])
        .agg(
            avg_throughput=("throughput_msg_s", "mean"),
            avg_p95_ms=("latency_p95_ms", "mean"),
            avg_loss_pct=("loss_rate_pct", "mean"),
        )
        .reset_index()
        .sort_values(["broker", "config", "target_rate"])
    )

    lines = [
        "| Broker | Config | Target msg/s | Avg throughput (msg/s)* | Avg p95 (ms)* | Avg loss (%)* |",
        "|--------|--------|-------------|--------------------------|--------------|---------------|",
    ]
    for _, row in agg.iterrows():
        broker_lbl = BROKER_LABELS.get(row["broker"], row["broker"])
        config_lbl = CONFIG_LABELS.get(row["config"], row["config"])
        lines.append(
            f"| {broker_lbl} | {config_lbl} | {int(row['target_rate']):,} | "
            f"{row['avg_throughput']:,.0f} | "
            f"{row['avg_p95_ms']:.2f} | "
            f"{row['avg_loss_pct']:.2f} |"
        )
    lines.append("")
    lines.append(
        "_Averages are over message sizes only (same broker, config, and target rate)._"
    )
    lines.append(
        "_`Avg loss (%)` is the mean of `lost_count / sent_count × 100` per row "
        "(`lost_count` = seq-gap estimate from the consumer)._"
    )
    return "\n".join(lines)


def write_report(
    charts_dir: Path,
    output_dir: Path,
    chart_paths: list[Path],
    summary_table: str,
    total_runs: int,
    *,
    report_filename: str = "report.md",
    heading: str = "# RabbitMQ vs Redis Streams — Benchmark Report",
    methodology_extra: str = "",
    generator_note: str = "*Generated automatically by `runner/report.py`*",
    reproduce_extra: str = "",
) -> Path:
    rel = lambda p: p.relative_to(output_dir)  # noqa: E731

    chart_sections = [
        ("Throughput vs Message Size", chart_paths[0]),
        ("p95 Latency vs Message Size", chart_paths[1]),
        ("Throughput vs Target Rate (Degradation Curve)", chart_paths[2]),
        ("p95 Latency vs Target Rate", chart_paths[3]),
        ("Message Loss Rate vs Target Rate", chart_paths[4]),
    ]

    sections = []
    for title, path in chart_sections:
        sections.append(f"### {title}\n\n![{title}]({rel(path)})\n")

    charts_block = "\n".join(sections)
    extra_method = f"\n{methodology_extra}\n" if methodology_extra.strip() else ""
    extra_repro = f"\n{reproduce_extra}\n" if reproduce_extra.strip() else ""

    report = f"""{heading}

## Summary

{summary_table}

> Total experiment runs: **{total_runs}**

---

## Charts

{charts_block}

---

## Methodology

- **Brokers**: RabbitMQ 3.13, Redis 7.2 (Streams)
- **Resource limits**: 2 CPU / 1 GB RAM per broker container
- **Configs tested**:
  - `durable_ack` — RabbitMQ: durable queue + publisher confirms + consumer ack; Redis: AOF enabled + XACK
  - `inmemory_noack` — RabbitMQ: transient queue, no confirms; Redis: no AOF, no XACK
- **Latency measurement**: `send_ts` embedded in each message body (monotonic clock); computed consumer-side as `recv_time - send_ts`
- **Warmup (steady metrics)**: first `warmup_seconds` after the **first received message** are excluded from latency samples and from steady throughput (`recv_steady` / steady wall time). Total `recv_count` still includes warmup messages.
- **Loss rate in charts**: `lost_count / sent_count × 100`, where **`lost_count`** is the consumer’s **sequence-gap** estimate (gaps in `seq` among received messages); compare `sent_count` vs `recv_count` for end-to-end delivery.
- **Rate control**: async token-bucket limiter in the producer
- **Charts**: throughput/latency vs **size** use one column per **target rate** (no averaging across rates). vs **rate** charts use one column per **message size** (no averaging across sizes).{extra_method}

---

## How to Reproduce

```bash
# 1. Start brokers and services
docker compose up --build -d

# 2. Wait for healthchecks to pass (~30s), then run
cd runner
pip install httpx
python runner.py --duration 60

# 3. Generate this report
python report.py
```
{extra_repro}
---

{generator_note}
"""

    report_path = output_dir / report_filename
    report_path.write_text(report)
    return report_path


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"Error: {input_path} not found. Run runner.py first.")
        raise SystemExit(1)

    print(f"Loading {input_path} ...")
    df = load_data(str(input_path))
    print(f"  {len(df)} rows, {df['broker'].nunique()} brokers, {df['config'].nunique()} configs")

    print("Generating charts ...")
    chart_paths = [
        chart_throughput_vs_size(df, charts_dir),
        chart_p95_latency_vs_size(df, charts_dir),
        chart_throughput_vs_rate(df, charts_dir),
        chart_p95_latency_vs_rate(df, charts_dir),
        chart_loss_rate_vs_rate(df, charts_dir),
    ]
    for p in chart_paths:
        print(f"  Saved {p}")

    print("Building summary table ...")
    summary = build_summary_table(df)

    print("Writing report.md ...")
    report_path = write_report(charts_dir, output_dir, chart_paths, summary, len(df))
    print(f"  Report written to {report_path}")


if __name__ == "__main__":
    main()
