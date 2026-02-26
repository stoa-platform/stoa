#!/usr/bin/env python3
"""Performance regression detector — compares PR benchmark results against main baseline.

Reads k6 JSON summaries from baseline and PR directories, compares p95 latency
per scenario. Outputs PASS/WARN/FAIL verdict.

Thresholds:
  - >10% regression -> FAIL
  - >5% regression  -> WARN
  - <=5%            -> PASS
  - >5% error rate  -> FAIL (regardless of latency)

Usage:
  python3 compare_results.py <baseline_dir> <pr_dir> [--fail-on-warn]

Exit codes:
  0 -- PASS or WARN (default)
  1 -- FAIL (or WARN with --fail-on-warn)

Uses stdlib only (no scipy/numpy).
"""

import json
import sys
from pathlib import Path

# Scenarios matching benchmark-ci.js
SCENARIOS = ["health", "sequential", "burst_50"]

# Regression thresholds (fraction, not percent)
FAIL_THRESHOLD = 0.10  # >10% = FAIL
WARN_THRESHOLD = 0.05  # >5% = WARN

# Error rate threshold
ERROR_RATE_THRESHOLD = 0.05  # >5% check failures = FAIL


def extract_p95(json_path: Path) -> float:
    """Extract p95 latency (ms) from a k6 JSON summary file."""
    if not json_path.exists():
        return 0.0
    try:
        data = json.loads(json_path.read_text())
        return float(
            data.get("metrics", {})
            .get("http_req_duration", {})
            .get("values", {})
            .get("p(95)", 0)
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0.0


def extract_error_rate(json_path: Path) -> float:
    """Extract error rate (1 - check pass rate) from a k6 JSON summary file."""
    if not json_path.exists():
        return 0.0
    try:
        data = json.loads(json_path.read_text())
        rate = float(
            data.get("metrics", {})
            .get("checks", {})
            .get("values", {})
            .get("rate", 1.0)
        )
        return max(0.0, 1.0 - rate)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0.0


def compare_scenario(
    scenario: str, baseline_dir: Path, pr_dir: Path
) -> dict:
    """Compare a single scenario between baseline and PR.

    Returns a dict with: scenario, baseline_p95_ms, pr_p95_ms,
    regression_pct, verdict, reason.
    """
    baseline_p95 = extract_p95(baseline_dir / f"{scenario}.json")
    pr_p95 = extract_p95(pr_dir / f"{scenario}.json")
    pr_error_rate = extract_error_rate(pr_dir / f"{scenario}.json")

    # Compute regression percentage
    if baseline_p95 > 0:
        regression_pct = round(((pr_p95 - baseline_p95) / baseline_p95) * 100, 1)
    else:
        # No baseline -- can't compute regression, pass by default
        regression_pct = 0.0

    # Determine verdict
    verdict = "PASS"
    reason = ""

    if pr_error_rate > ERROR_RATE_THRESHOLD:
        verdict = "FAIL"
        reason = f"High error rate: {pr_error_rate:.1%}"
    elif baseline_p95 > 0 and (pr_p95 - baseline_p95) / baseline_p95 > FAIL_THRESHOLD:
        verdict = "FAIL"
        reason = f"p95 regression {regression_pct}% exceeds {FAIL_THRESHOLD:.0%} threshold"
    elif baseline_p95 > 0 and (pr_p95 - baseline_p95) / baseline_p95 > WARN_THRESHOLD:
        verdict = "WARN"
        reason = f"p95 regression {regression_pct}% exceeds {WARN_THRESHOLD:.0%} warning threshold"
    else:
        reason = "Within acceptable range"

    return {
        "scenario": scenario,
        "baseline_p95_ms": baseline_p95,
        "pr_p95_ms": pr_p95,
        "regression_pct": regression_pct,
        "error_rate": round(pr_error_rate, 3),
        "verdict": verdict,
        "reason": reason,
    }


def main() -> int:
    """Compare all scenarios and return exit code."""
    args = sys.argv[1:]
    fail_on_warn = "--fail-on-warn" in args
    args = [a for a in args if not a.startswith("--")]

    if len(args) < 2:
        print(f"Usage: {sys.argv[0]} <baseline_dir> <pr_dir> [--fail-on-warn]", file=sys.stderr)
        return 2

    baseline_dir = Path(args[0])
    pr_dir = Path(args[1])

    results = []
    has_fail = False
    has_warn = False

    print("\n=== Performance Regression Report ===\n")

    for scenario in SCENARIOS:
        result = compare_scenario(scenario, baseline_dir, pr_dir)
        results.append(result)

        icon = {"PASS": "OK", "WARN": "!!", "FAIL": "XX"}[result["verdict"]]
        print(
            f"  [{icon}] {scenario:>12s}: "
            f"baseline={result['baseline_p95_ms']:.1f}ms "
            f"pr={result['pr_p95_ms']:.1f}ms "
            f"delta={result['regression_pct']:+.1f}% "
            f"--- {result['verdict']}"
        )

        if result["verdict"] == "FAIL":
            has_fail = True
        elif result["verdict"] == "WARN":
            has_warn = True

    # Overall verdict
    if has_fail:
        overall = "FAIL"
    elif has_warn:
        overall = "WARN"
    else:
        overall = "PASS"

    print(f"\n  Overall: {overall}\n")

    # Write JSON report
    report = {
        "overall_verdict": overall,
        "scenarios": results,
        "thresholds": {
            "warn_pct": int(WARN_THRESHOLD * 100),
            "fail_pct": int(FAIL_THRESHOLD * 100),
        },
    }

    pr_dir.mkdir(parents=True, exist_ok=True)
    report_path = pr_dir / "regression-report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"  Report written to {report_path}")

    # Exit code
    if has_fail:
        return 1
    if has_warn and fail_on_warn:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
