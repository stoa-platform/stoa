#!/usr/bin/env python3
"""STOA Bench Runner — Orchestrates L2 CUJ tests and pushes metrics.

Runs pytest on L2 CUJ tests, collects JSON results, computes summary,
pushes to Prometheus Pushgateway, and handles alerting.

Usage:
    # Run all L2 CUJs
    python runner.py

    # Run specific CUJ
    python runner.py --cuj CUJ-01

    # Dry run (no push)
    python runner.py --dry-run

    # CronJob mode (exit code reflects demo_ready)
    python runner.py --cron

Environment variables:
    STOA_API_URL, STOA_GATEWAY_URL, STOA_AUTH_URL — service endpoints
    BENCH_ADMIN_CLIENT_SECRET — Keycloak credentials
    PUSHGATEWAY_URL, PUSHGATEWAY_AUTH — metrics push
    HEALTHCHECKS_URL — dead man's switch (optional)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RESULTS_DIR = Path("/tmp/stoa-bench-results")
BENCH_DIR = Path(__file__).parent


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(json.dumps({"time": ts, "level": "INFO", "msg": msg}), file=sys.stderr)


def run_l2_tests(cuj_filter: str | None = None) -> int:
    """Run pytest on L2 CUJ tests. Returns exit code."""
    # Clean previous results
    if RESULTS_DIR.exists():
        shutil.rmtree(RESULTS_DIR)
    RESULTS_DIR.mkdir(parents=True)

    cmd = [
        sys.executable, "-m", "pytest",
        str(BENCH_DIR / "tests" / "l2_cuj"),
        "-v",
        "--tb=short",
        f"--rootdir={BENCH_DIR}",
    ]

    if cuj_filter:
        # Map CUJ-01 → test_cuj01, CUJ-05 → test_cuj05
        test_name = f"test_{cuj_filter.lower().replace('-', '')}"
        cmd.extend(["-k", test_name])

    env = {**os.environ, "PYTHONPATH": str(BENCH_DIR)}

    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, capture_output=False)
    return result.returncode


def collect_and_report(dry_run: bool = False) -> dict:
    """Collect CUJ results and generate L2 summary, then run L3 analysis."""
    # Import here to avoid circular deps when running as script
    sys.path.insert(0, str(BENCH_DIR))
    from scoring.l2_reporter import aggregate_results, push_l2_metrics
    from scoring.l3_analyzer import analyze_stability, append_l2_result
    from scoring.push_metrics import MetricsPusher

    if not RESULTS_DIR.exists() or not list(RESULTS_DIR.glob("cuj_*.json")):
        log("No CUJ result files found")
        return {"demo_ready": False, "summary": "0/0 CUJs PASS", "demo_note": "NO RESULTS"}

    summary = aggregate_results(RESULTS_DIR)

    # Append to L3 history (always, even in dry-run — history is local)
    append_l2_result(summary)
    log("L2 result appended to L3 history")

    # Run L3 stability analysis
    l3_result = analyze_stability()
    summary["l3"] = l3_result.to_dict()
    log(
        f"L3: consecutive={l3_result.consecutive_l2_pass} "
        f"confidence={l3_result.demo_confidence} "
        f"regressions={len(l3_result.regressions_detected)} "
        f"flaky={len(l3_result.flaky_cujs)}"
    )

    # Print summary to stdout (structured JSON)
    print(json.dumps(summary, indent=2))

    if not dry_run:
        # Push L2 metrics
        status_code = push_l2_metrics(summary)
        if 200 <= status_code < 300:
            log(f"L2 metrics pushed to Pushgateway (HTTP {status_code})")
        elif status_code == 0:
            log("WARNING: Pushgateway unreachable")
        else:
            log(f"WARNING: Pushgateway returned HTTP {status_code}")

        # Push L3 metrics
        l3_status = _push_l3_metrics(l3_result)
        if 200 <= l3_status < 300:
            log(f"L3 metrics pushed to Pushgateway (HTTP {l3_status})")

    return summary


def _push_l3_metrics(l3_result) -> int:
    """Push L3 stability metrics to Pushgateway."""
    from scoring.push_metrics import MetricsPusher

    pusher = MetricsPusher()

    pusher.add_gauge(
        "stoa_bench_l3_consecutive_pass",
        l3_result.consecutive_l2_pass,
        help_text="Number of consecutive L2 PASS runs",
    )
    pusher.add_gauge(
        "stoa_bench_l3_demo_confidence",
        {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "BLOCKED": 0}.get(
            l3_result.demo_confidence, 0
        ),
        help_text="Demo confidence level (0=blocked, 1=low, 2=medium, 3=high)",
    )
    pusher.add_gauge(
        "stoa_bench_l3_regressions",
        len(l3_result.regressions_detected),
        help_text="Number of latency regressions detected",
    )
    pusher.add_gauge(
        "stoa_bench_l3_flaky_cujs",
        len(l3_result.flaky_cujs),
        help_text="Number of flaky CUJs (pass rate < 95%)",
    )

    # Per-service availability (if populated)
    for svc, avail in l3_result.availability_24h.items():
        pusher.add_gauge(
            "stoa_bench_l3_availability_24h",
            avail,
            {"service": svc},
            help_text="24h service availability percentage",
        )

    # L3-04: Per-CUJ error rates
    for cuj_id, error_pct in l3_result.error_rates.items():
        pusher.add_gauge(
            "stoa_bench_l3_error_rate",
            error_pct,
            {"cuj": cuj_id},
            help_text="CUJ error rate percentage (last 20 runs)",
        )

    # Error trend: -1=improving, 0=stable, 1=degrading
    trend_val = {"improving": -1, "stable": 0, "degrading": 1}.get(
        l3_result.error_trend, 0
    )
    pusher.add_gauge(
        "stoa_bench_l3_error_trend",
        trend_val,
        help_text="Error rate trend (-1=improving, 0=stable, 1=degrading)",
    )

    pusher.add_gauge(
        "stoa_bench_l3_last_run",
        time.time(),
        help_text="Unix timestamp of last L3 analysis",
    )

    return pusher.push(job="stoa_bench_l3")


def ping_healthchecks(success: bool) -> None:
    """Ping Healthchecks dead man's switch."""
    url = os.environ.get("HEALTHCHECKS_URL", "")
    if not url:
        return

    import httpx
    try:
        suffix = "" if success else "/fail"
        httpx.get(f"{url}{suffix}", timeout=5.0)
        log(f"Healthchecks pinged {'success' if success else 'fail'}")
    except Exception:
        log("WARNING: Healthchecks ping failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="STOA Bench Runner")
    parser.add_argument("--cuj", help="Run specific CUJ (e.g., CUJ-01)")
    parser.add_argument("--dry-run", action="store_true", help="Don't push metrics")
    parser.add_argument("--cron", action="store_true", help="CronJob mode (exit code = demo status)")
    args = parser.parse_args()

    log("STOA Bench L2 runner starting")

    # Run tests
    exit_code = run_l2_tests(cuj_filter=args.cuj)
    log(f"pytest exit code: {exit_code}")

    # Collect and report
    summary = collect_and_report(dry_run=args.dry_run)

    # Healthchecks
    if not args.dry_run:
        ping_healthchecks(summary.get("demo_ready", False))

    # Exit code
    if args.cron:
        # In cron mode: 0 = demo_ready, 1 = not ready
        sys.exit(0 if summary.get("demo_ready") else 1)
    else:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
