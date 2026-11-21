"""L2 CUJ Reporter — Aggregates CUJ results and pushes metrics.

Reads CUJ result JSON files from a directory, computes summary,
determines demo_ready status, and pushes to Prometheus.

Usage:
    python -m scoring.l2_reporter /tmp/stoa-bench-results/
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .push_metrics import MetricsPusher

# CUJ criticality for demo_ready determination
# CUJ-01 (API Discovery), CUJ-02 (Subscription), CUJ-05 (MCP Tool Exposure)
# are demo blockers — without self-service or MCP, no pitch on demo day.
DEMO_BLOCKERS = {"CUJ-01", "CUJ-02", "CUJ-05"}
DEMO_DEGRADED = {"CUJ-03", "CUJ-04"}  # observability + auth federation — nice-to-have


def aggregate_results(results_dir: Path) -> dict:
    """Read all CUJ result JSONs and produce the L2 summary."""
    cujs: dict[str, dict] = {}
    for f in sorted(results_dir.glob("cuj_*.json")):
        data = json.loads(f.read_text())
        cuj_id = data.get("cuj_id", f.stem)
        cujs[cuj_id] = data

    total = len(cujs)
    passed = sum(1 for c in cujs.values() if c.get("status") == "PASS")

    # Demo readiness logic
    # Only count a CUJ as blocker if it actually ran sub-tests
    # (a CUJ that failed before running any sub-tests is infrastructure-not-ready, not a real failure)
    def _is_real_failure(cid: str) -> bool:
        cuj = cujs.get(cid, {})
        if cuj.get("status") == "PASS":
            return False
        # If CUJ has sub_tests, it actually ran — count it
        return bool(cuj.get("sub_tests"))

    blocker_fail = any(
        _is_real_failure(cid) for cid in DEMO_BLOCKERS if cid in cujs
    )
    degraded_fail = any(
        cujs.get(cid, {}).get("status") != "PASS" for cid in DEMO_DEGRADED if cid in cujs
    )

    if blocker_fail:
        demo_ready = False
        demo_note = "BLOCKED — critical CUJ failing"
    elif degraded_fail:
        demo_ready = True
        demo_note = "DEGRADED — non-critical CUJ failing"
    elif passed == total and total >= 3:
        demo_ready = True
        demo_note = "GO"
    else:
        demo_ready = False
        demo_note = f"INSUFFICIENT — only {passed}/{total} CUJs pass"

    return {
        "layer": "L2",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cujs": cujs,
        "summary": f"{passed}/{total} CUJs PASS",
        "demo_ready": demo_ready,
        "demo_note": demo_note,
    }


def push_l2_metrics(summary: dict) -> int:
    """Push L2 results to Prometheus Pushgateway."""
    pusher = MetricsPusher()

    for cuj_id, cuj_data in summary.get("cujs", {}).items():
        status = 1 if cuj_data.get("status") == "PASS" else 0
        e2e_s = cuj_data.get("e2e_ms", 0) / 1000.0

        pusher.add_gauge(
            "stoa_bench_cuj_status",
            status,
            {"cuj": cuj_id, "layer": "L2"},
            help_text="CUJ pass (1) or fail (0)",
        )
        pusher.add_gauge(
            "stoa_bench_cuj_duration_seconds",
            round(e2e_s, 3),
            {"cuj": cuj_id, "layer": "L2"},
            help_text="CUJ end-to-end duration in seconds",
        )

        # Push sub-test details
        for sub_id, sub_data in cuj_data.get("sub_tests", {}).items():
            sub_status = 1 if sub_data.get("status") == "PASS" else 0
            pusher.add_gauge(
                "stoa_bench_subtest_status",
                sub_status,
                {"cuj": cuj_id, "subtest": sub_id, "layer": "L2"},
                help_text="Sub-test pass (1) or fail (0)",
            )

    # Summary metrics
    cujs = summary.get("cujs", {})
    total = len(cujs)
    passed = sum(1 for c in cujs.values() if c.get("status") == "PASS")

    pusher.add_gauge(
        "stoa_bench_l2_passed", passed, help_text="Number of L2 CUJs passed"
    )
    pusher.add_gauge(
        "stoa_bench_l2_total", total, help_text="Total number of L2 CUJs"
    )
    pusher.add_gauge(
        "stoa_bench_demo_ready",
        1 if summary.get("demo_ready") else 0,
        help_text="Demo readiness (1=ready, 0=blocked)",
    )
    pusher.add_gauge(
        "stoa_bench_l2_last_run",
        time.time(),
        help_text="Unix timestamp of last L2 run",
    )

    return pusher.push(job="stoa_bench_l2")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scoring.l2_reporter <results_dir>", file=sys.stderr)
        sys.exit(1)

    results_dir = Path(sys.argv[1])
    if not results_dir.is_dir():
        print(f"ERROR: {results_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    summary = aggregate_results(results_dir)
    print(json.dumps(summary, indent=2))

    status_code = push_l2_metrics(summary)
    if 200 <= status_code < 300:
        print(f"Metrics pushed to Pushgateway (HTTP {status_code})", file=sys.stderr)
    elif status_code == 0:
        print("WARNING: Pushgateway unreachable", file=sys.stderr)
    else:
        print(f"WARNING: Pushgateway returned HTTP {status_code}", file=sys.stderr)


if __name__ == "__main__":
    main()
