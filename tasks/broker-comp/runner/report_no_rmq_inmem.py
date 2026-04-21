#!/usr/bin/env python3
"""
Subset benchmark report — same charts and summary as report.py, but **excludes**
RabbitMQ `inmemory_noack` rows (volatile / no-confirm Rabbit path), which often
dominates scales and obscures other series.

Writes:
  results/report_no_rmq_inmem/report.md
  results/report_no_rmq_inmem/charts/*.png

Usage:
  python report_no_rmq_inmem.py [--input PATH] [--output-dir PATH]

Requires the same dependencies as report.py (pandas, matplotlib).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import report as base_report

DEFAULT_INPUT = Path(__file__).parent.parent / "results" / "results.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "results" / "report_no_rmq_inmem"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark report without RabbitMQ in-memory / no-ack")
    p.add_argument("--input", type=str, default=str(DEFAULT_INPUT))
    p.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    return p.parse_args()


def exclude_rmq_inmemory(df):
    mask = ~((df["broker"] == "rmq") & (df["config"] == "inmemory_noack"))
    return df.loc[mask].copy()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.is_file():
        print(f"Error: {input_path} not found. Run runner.py first.", file=sys.stderr)
        raise SystemExit(1)

    print(f"Loading {input_path} ...")
    df = base_report.load_data(str(input_path))
    n_before = len(df)
    df = exclude_rmq_inmemory(df)
    n_after = len(df)
    print(f"  Excluded RabbitMQ in-memory / no-ack: {n_before} -> {n_after} rows")
    if n_after == 0:
        print("Error: no rows left after filter.", file=sys.stderr)
        raise SystemExit(1)

    print("Generating charts ...")
    chart_paths = [
        base_report.chart_throughput_vs_size(df, charts_dir),
        base_report.chart_p95_latency_vs_size(df, charts_dir),
        base_report.chart_throughput_vs_rate(df, charts_dir),
        base_report.chart_p95_latency_vs_rate(df, charts_dir),
        base_report.chart_loss_rate_vs_rate(df, charts_dir),
    ]
    for p in chart_paths:
        print(f"  Saved {p}")

    print("Building summary table ...")
    summary = base_report.build_summary_table(df)

    print("Writing report.md ...")
    report_path = base_report.write_report(
        charts_dir,
        output_dir,
        chart_paths,
        summary,
        len(df),
        report_filename="report.md",
        heading="# RabbitMQ vs Redis Streams — Benchmark Report (excl. RabbitMQ in-memory / no-ack)",
        methodology_extra=(
            "- **This document**: charts and summary use only rows where it is **not** "
            "(`broker` = `rmq` and `config` = `inmemory_noack`). "
            "Redis `inmemory_noack` and RabbitMQ `durable_ack` are still included."
        ),
        generator_note="*Generated automatically by `runner/report_no_rmq_inmem.py`*",
        reproduce_extra=(
            "\nSubset report (after `results.csv` exists):\n\n"
            "```bash\ncd runner\npython report_no_rmq_inmem.py\n```\n"
        ),
    )
    print(f"  Report written to {report_path}")


if __name__ == "__main__":
    main()
