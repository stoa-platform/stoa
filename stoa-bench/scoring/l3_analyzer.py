"""L3 Stability Analyzer — Regression detection, flakiness, demo confidence.

Reads historical L2 results from Prometheus (or local JSON cache) to compute
stability metrics: consecutive pass count, latency regression, CUJ flakiness.

Usage:
    from scoring.l3_analyzer import analyze_stability

    result = analyze_stability(history)
    # result = {
    #   "consecutive_l2_pass": 47,
    #   "stability_status": "stable",
    #   "regressions_detected": [],
    #   "flaky_cujs": [],
    #   "demo_confidence": "HIGH"
    # }
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

# L3 history file (append-only JSON lines)
HISTORY_FILE = Path("/tmp/stoa-bench-history/l2_history.jsonl")


@dataclass
class L3Result:
    consecutive_l2_pass: int = 0
    stability_status: str = "unknown"  # stable, degraded, unstable
    regressions_detected: list[str] = field(default_factory=list)
    availability_24h: dict[str, float] = field(default_factory=dict)
    flaky_cujs: list[str] = field(default_factory=list)
    demo_confidence: str = "BLOCKED"  # HIGH, MEDIUM, LOW, BLOCKED
    error_rates: dict[str, float] = field(default_factory=dict)  # L3-04: per-CUJ error %
    error_trend: str = "stable"  # improving, stable, degrading

    def to_dict(self) -> dict:
        return {
            "layer": "L3",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "consecutive_l2_pass": self.consecutive_l2_pass,
            "stability_status": self.stability_status,
            "regressions_detected": self.regressions_detected,
            "availability_24h": self.availability_24h,
            "flaky_cujs": self.flaky_cujs,
            "demo_confidence": self.demo_confidence,
            "error_rates": self.error_rates,
            "error_trend": self.error_trend,
        }


def append_l2_result(l2_summary: dict) -> None:
    """Append an L2 run result to the history file."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": l2_summary.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "demo_ready": l2_summary.get("demo_ready", False),
        "cujs": {
            cuj_id: {
                "status": data.get("status", "FAIL"),
                "e2e_ms": data.get("e2e_ms", 0),
            }
            for cuj_id, data in l2_summary.get("cujs", {}).items()
        },
    }
    with HISTORY_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def load_history(max_entries: int = 500) -> list[dict]:
    """Load L2 history from JSONL file."""
    if not HISTORY_FILE.exists():
        return []

    entries = []
    for line in HISTORY_FILE.read_text().strip().split("\n"):
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return entries[-max_entries:]


def analyze_stability(history: list[dict] | None = None) -> L3Result:
    """Analyze L2 history for stability metrics."""
    if history is None:
        history = load_history()

    result = L3Result()

    if not history:
        result.demo_confidence = "BLOCKED"
        result.stability_status = "unknown"
        return result

    # L3-01: Consecutive PASS count (from most recent backward)
    consecutive = 0
    for entry in reversed(history):
        if entry.get("demo_ready", False):
            consecutive += 1
        else:
            break
    result.consecutive_l2_pass = consecutive

    # L3-02/03: Latency regression (compare last 3 vs previous 10)
    if len(history) >= 13:
        recent = history[-3:]
        baseline = history[-13:-3]
        _check_regression(result, recent, baseline)

    # L3-06: CUJ flakiness (last 7 days / ~672 runs at 15min intervals)
    # Use last 100 entries as proxy
    recent_window = history[-100:] if len(history) >= 100 else history
    _check_flakiness(result, recent_window)

    # L3-04: Error rate trend (compare last 20 vs previous 20)
    _check_error_rates(result, history)

    # Demo confidence
    if result.consecutive_l2_pass >= 50 and not result.regressions_detected and not result.flaky_cujs:
        result.demo_confidence = "HIGH"
        result.stability_status = "stable"
    elif result.consecutive_l2_pass >= 10:
        result.demo_confidence = "MEDIUM"
        result.stability_status = "degraded" if result.flaky_cujs else "stable"
    elif result.consecutive_l2_pass > 0:
        result.demo_confidence = "LOW"
        result.stability_status = "unstable"
    else:
        result.demo_confidence = "BLOCKED"
        result.stability_status = "unstable"

    return result


def _check_regression(
    result: L3Result,
    recent: list[dict],
    baseline: list[dict],
) -> None:
    """Check for latency regression between recent and baseline windows."""
    # Aggregate e2e_ms per CUJ
    cuj_ids: set[str] = set()
    for entry in recent + baseline:
        cuj_ids.update(entry.get("cujs", {}).keys())

    for cuj_id in cuj_ids:
        recent_latencies = [
            entry["cujs"][cuj_id]["e2e_ms"]
            for entry in recent
            if cuj_id in entry.get("cujs", {}) and entry["cujs"][cuj_id].get("e2e_ms", 0) > 0
        ]
        baseline_latencies = [
            entry["cujs"][cuj_id]["e2e_ms"]
            for entry in baseline
            if cuj_id in entry.get("cujs", {}) and entry["cujs"][cuj_id].get("e2e_ms", 0) > 0
        ]

        if not recent_latencies or not baseline_latencies:
            continue

        recent_avg = sum(recent_latencies) / len(recent_latencies)
        baseline_avg = sum(baseline_latencies) / len(baseline_latencies)

        if baseline_avg > 0:
            degradation_pct = ((recent_avg - baseline_avg) / baseline_avg) * 100
            if degradation_pct > 15:  # 15% threshold
                result.regressions_detected.append(
                    f"{cuj_id}: +{degradation_pct:.0f}% latency ({baseline_avg:.0f}ms → {recent_avg:.0f}ms)"
                )


def _check_flakiness(result: L3Result, window: list[dict]) -> None:
    """Check CUJ flakiness (pass ratio < 95% = flaky)."""
    cuj_stats: dict[str, dict[str, int]] = {}

    for entry in window:
        for cuj_id, cuj_data in entry.get("cujs", {}).items():
            if cuj_id not in cuj_stats:
                cuj_stats[cuj_id] = {"pass": 0, "total": 0}
            cuj_stats[cuj_id]["total"] += 1
            if cuj_data.get("status") == "PASS":
                cuj_stats[cuj_id]["pass"] += 1

    for cuj_id, stats in cuj_stats.items():
        if stats["total"] > 0:
            ratio = stats["pass"] / stats["total"]
            if ratio < 0.95:
                result.flaky_cujs.append(
                    f"{cuj_id}: {ratio*100:.1f}% pass rate ({stats['pass']}/{stats['total']})"
                )


def _check_error_rates(result: L3Result, history: list[dict]) -> None:
    """L3-04: Compute per-CUJ error rates and detect trend (improving/degrading/stable).

    Compares the error rate of the last 20 runs vs the previous 20 runs.
    If the recent error rate dropped by >5pp → improving.
    If the recent error rate rose by >5pp → degrading.
    Otherwise → stable.
    """
    if len(history) < 5:
        return

    # Current error rates (last 20 runs)
    recent = history[-20:]
    cuj_errors: dict[str, dict[str, int]] = {}
    for entry in recent:
        for cuj_id, cuj_data in entry.get("cujs", {}).items():
            if cuj_id not in cuj_errors:
                cuj_errors[cuj_id] = {"fail": 0, "total": 0}
            cuj_errors[cuj_id]["total"] += 1
            if cuj_data.get("status") != "PASS":
                cuj_errors[cuj_id]["fail"] += 1

    for cuj_id, stats in cuj_errors.items():
        if stats["total"] > 0:
            result.error_rates[cuj_id] = round(
                (stats["fail"] / stats["total"]) * 100, 1
            )

    # Trend detection: compare last 20 vs previous 20
    if len(history) < 40:
        result.error_trend = "stable"
        return

    previous = history[-40:-20]
    prev_errors: dict[str, dict[str, int]] = {}
    for entry in previous:
        for cuj_id, cuj_data in entry.get("cujs", {}).items():
            if cuj_id not in prev_errors:
                prev_errors[cuj_id] = {"fail": 0, "total": 0}
            prev_errors[cuj_id]["total"] += 1
            if cuj_data.get("status") != "PASS":
                prev_errors[cuj_id]["fail"] += 1

    # Compare aggregate error rates
    recent_total_fail = sum(s["fail"] for s in cuj_errors.values())
    recent_total = sum(s["total"] for s in cuj_errors.values())
    prev_total_fail = sum(s["fail"] for s in prev_errors.values())
    prev_total = sum(s["total"] for s in prev_errors.values())

    if recent_total == 0 or prev_total == 0:
        result.error_trend = "stable"
        return

    recent_rate = recent_total_fail / recent_total
    prev_rate = prev_total_fail / prev_total
    delta = recent_rate - prev_rate  # positive = more errors

    if delta > 0.05:
        result.error_trend = "degrading"
    elif delta < -0.05:
        result.error_trend = "improving"
    else:
        result.error_trend = "stable"
