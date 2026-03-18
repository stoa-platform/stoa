# Copyright 2026 CAB Ingénierie — Apache 2.0
"""Generate a markdown report from locust CSV output.

Reads the *_stats.csv and *_stats_history.csv files produced by
`locust --csv <prefix>` and outputs a human-readable markdown report.

Usage:
    python -m benchmarks.report results/bench
"""

import contextlib
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path


def load_stats(csv_prefix: str) -> list[dict]:
    """Load the stats summary CSV."""
    stats_file = Path(f"{csv_prefix}_stats.csv")
    if not stats_file.exists():
        print(f"Error: {stats_file} not found", file=sys.stderr)
        sys.exit(1)

    with stats_file.open() as f:
        reader = csv.DictReader(f)
        return list(reader)


def format_latency(ms_str: str) -> str:
    """Format milliseconds for display."""
    try:
        ms = float(ms_str)
    except (ValueError, TypeError):
        return "N/A"
    if ms < 1:
        return f"{ms * 1000:.0f}us"
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    return f"{ms:.0f}ms"


def generate_report(csv_prefix: str) -> str:
    """Generate markdown report from locust CSV files."""
    rows = load_stats(csv_prefix)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "# STOA Control Plane API — Benchmark Report",
        "",
        f"_Generated: {now}_",
        "",
        "## Summary",
        "",
        "| Endpoint | Requests | Failures | Median (ms) | P95 (ms) | P99 (ms) | Avg (ms) | RPS |",
        "|----------|----------|----------|-------------|----------|----------|----------|-----|",
    ]

    aggregated = None
    for row in rows:
        name = row.get("Name", "")
        if name == "Aggregated":
            aggregated = row
            continue

        req_count = row.get("Request Count", "0")
        fail_count = row.get("Failure Count", "0")
        median = format_latency(row.get("Median Response Time", "0"))
        p95 = format_latency(row.get("95%", "0"))
        p99 = format_latency(row.get("99%", "0"))
        avg = format_latency(row.get("Average Response Time", "0"))
        rps = row.get("Requests/s", "0")
        with contextlib.suppress(ValueError):
            rps = f"{float(rps):.1f}"

        lines.append(f"| {name} | {req_count} | {fail_count} | {median} | {p95} | {p99} | {avg} | {rps} |")

    lines.append("")

    if aggregated:
        total_req = aggregated.get("Request Count", "0")
        total_fail = aggregated.get("Failure Count", "0")
        total_rps = aggregated.get("Requests/s", "0")
        with contextlib.suppress(ValueError):
            total_rps = f"{float(total_rps):.1f}"
        avg_latency = format_latency(aggregated.get("Average Response Time", "0"))
        p95_latency = format_latency(aggregated.get("95%", "0"))

        lines.extend(
            [
                "## Totals",
                "",
                f"- **Total Requests**: {total_req}",
                f"- **Total Failures**: {total_fail}",
                f"- **Aggregate RPS**: {total_rps}",
                f"- **Avg Latency**: {avg_latency}",
                f"- **P95 Latency**: {p95_latency}",
                "",
            ]
        )

    # Threshold check
    from .config import THRESHOLDS

    violations = []
    for row in rows:
        name = row.get("Name", "")
        if name == "Aggregated":
            continue
        p95_raw = row.get("95%", "0")
        try:
            p95_val = float(p95_raw)
        except ValueError:
            continue

        for key, threshold_ms in THRESHOLDS.items():
            if key.replace("_", "/") in name.lower() or key in name.lower():
                status = "PASS" if p95_val <= threshold_ms else "FAIL"
                violations.append(f"| {name} | {p95_val:.0f}ms | {threshold_ms}ms | {status} |")
                break

    if violations:
        lines.extend(
            [
                "## Threshold Check",
                "",
                "| Endpoint | P95 | Threshold | Status |",
                "|----------|-----|-----------|--------|",
                *violations,
                "",
            ]
        )

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m benchmarks.report <csv_prefix>", file=sys.stderr)
        sys.exit(1)

    report = generate_report(sys.argv[1])
    print(report)
