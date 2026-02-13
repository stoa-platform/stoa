#!/usr/bin/env python3
"""Arena Score Aggregator — Computes median scores + CI95 from k6 run summaries.

Called by run-arena.sh after all k6 runs complete. Reads JSON summaries,
computes per-gateway median scores, stddev, and 95% confidence intervals.
Outputs Prometheus text metrics to stdout (piped to curl for Pushgateway).

Uses stdlib only (no scipy/numpy) — manual t-distribution critical values.

Usage:
  python3 run-arena.py <work_dir> <gateways_json>
"""

import json
import math
import os
import sys
from pathlib import Path

# t-distribution critical values for 95% CI (two-tailed, alpha=0.05)
# Key = degrees of freedom (n-1), value = t(0.975, df)
T_TABLE = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    15: 2.131, 20: 2.086, 30: 2.042, 60: 2.000, 120: 1.980,
}

# Scoring caps (same as shell version)
CAP_BASE = 0.4
CAP_BURST50 = 2.5
CAP_BURST100 = 4.0

# Weights
W_BASE = 0.15
W_BURST50 = 0.25
W_BURST100 = 0.25
W_AVAIL = 0.15
W_ERROR = 0.10
W_CONSIST = 0.10

SCENARIOS = ["health", "sequential", "burst_10", "burst_50", "burst_100", "sustained"]


def t_critical(df: int) -> float:
    """Look up t-critical value for given degrees of freedom."""
    if df in T_TABLE:
        return T_TABLE[df]
    # Find closest key
    keys = sorted(T_TABLE.keys())
    for i, k in enumerate(keys):
        if k >= df:
            return T_TABLE[k]
    return 1.96  # fallback to z-score for large df


def extract_pct(json_path: Path, key: str) -> float:
    """Extract a percentile from k6 JSON summary (returns seconds)."""
    if not json_path.exists():
        return 0.0
    try:
        data = json.loads(json_path.read_text())
        ms = data.get("metrics", {}).get("http_req_duration", {}).get("values", {}).get(key, 0)
        return ms / 1000.0
    except (json.JSONDecodeError, KeyError):
        return 0.0


def extract_checks(json_path: Path, field: str) -> int:
    """Extract check pass/fail count."""
    if not json_path.exists():
        return 0
    try:
        data = json.loads(json_path.read_text())
        return int(data.get("metrics", {}).get("checks", {}).get("values", {}).get(field, 0))
    except (json.JSONDecodeError, KeyError, ValueError):
        return 0


def median(values: list[float]) -> float:
    """Compute median of a list."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2]


def latency_score(p95: float, cap: float) -> float:
    """Score: 100 * (1 - p95/cap), clamped [0, 100]."""
    return max(0.0, min(100.0, 100.0 * (1.0 - p95 / cap)))


def compute_gateway_score(scenario_medians: dict, total_ok: int, total_req: int) -> float:
    """Compute composite arena score from median values."""
    base = latency_score(scenario_medians.get("sequential", {}).get("p95", 0), CAP_BASE)
    b50 = latency_score(scenario_medians.get("burst_50", {}).get("p95", 0), CAP_BURST50)
    b100 = latency_score(scenario_medians.get("burst_100", {}).get("p95", 0), CAP_BURST100)

    avail = 100.0 * (total_ok / total_req) if total_req > 0 else 50.0
    error = avail  # same formula

    # IQR-based consistency on sustained
    sus = scenario_medians.get("sustained", {})
    p25, p50, p75 = sus.get("p25", 0), sus.get("p50", 0), sus.get("p75", 0)
    if p50 > 0:
        iqr_cv = (p75 - p25) / p50
        consist = max(0.0, min(100.0, 100.0 * (1.0 - iqr_cv)))
    else:
        consist = 100.0

    score = W_BASE * base + W_BURST50 * b50 + W_BURST100 * b100 + W_AVAIL * avail + W_ERROR * error + W_CONSIST * consist
    return max(0.0, min(100.0, score))


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <work_dir> <gateways_json>", file=sys.stderr)
        sys.exit(1)

    work_dir = Path(sys.argv[1])
    gateways = json.loads(sys.argv[2])
    discard_first = int(os.environ.get("DISCARD_FIRST", "1"))
    total_runs = int(os.environ.get("RUNS", "5"))

    lines = []  # Prometheus text format
    lines.append("# HELP gateway_arena_score Composite arena score 0-100")
    lines.append("# TYPE gateway_arena_score gauge")
    lines.append("# HELP gateway_arena_availability Gateway availability 0-1")
    lines.append("# TYPE gateway_arena_availability gauge")
    lines.append("# HELP gateway_arena_score_stddev Run-to-run standard deviation")
    lines.append("# TYPE gateway_arena_score_stddev gauge")
    lines.append("# HELP gateway_arena_score_ci_lower CI95 lower bound")
    lines.append("# TYPE gateway_arena_score_ci_lower gauge")
    lines.append("# HELP gateway_arena_score_ci_upper CI95 upper bound")
    lines.append("# TYPE gateway_arena_score_ci_upper gauge")
    lines.append("# HELP gateway_arena_runs Number of valid runs after discard")
    lines.append("# TYPE gateway_arena_runs gauge")
    lines.append("# HELP gateway_arena_p50_seconds P50 latency")
    lines.append("# TYPE gateway_arena_p50_seconds gauge")
    lines.append("# HELP gateway_arena_p95_seconds P95 latency")
    lines.append("# TYPE gateway_arena_p95_seconds gauge")
    lines.append("# HELP gateway_arena_p99_seconds P99 latency")
    lines.append("# TYPE gateway_arena_p99_seconds gauge")
    lines.append("# HELP gateway_arena_requests_total Total requests by status")
    lines.append("# TYPE gateway_arena_requests_total counter")

    leaderboard = []

    for gw in gateways:
        name = gw["name"]
        gw_dir = work_dir / name
        valid_runs = list(range(discard_first + 1, total_runs + 1))
        n = len(valid_runs)

        # Collect per-scenario per-run data
        scenario_run_data: dict[str, list[dict]] = {s: [] for s in SCENARIOS}

        for run in valid_runs:
            for scenario in SCENARIOS:
                jf = gw_dir / f"run-{run}" / f"{scenario}.json"
                scenario_run_data[scenario].append({
                    "p25": extract_pct(jf, "p(25)"),
                    "p50": extract_pct(jf, "p(50)"),
                    "p75": extract_pct(jf, "p(75)"),
                    "p95": extract_pct(jf, "p(95)"),
                    "p99": extract_pct(jf, "p(99)"),
                    "ok": extract_checks(jf, "passes"),
                    "fail": extract_checks(jf, "fails"),
                })

        # Compute medians per scenario
        scenario_medians = {}
        total_ok = 0
        total_req = 0

        for scenario in SCENARIOS:
            runs = scenario_run_data[scenario]
            med = {
                "p25": median([r["p25"] for r in runs]),
                "p50": median([r["p50"] for r in runs]),
                "p75": median([r["p75"] for r in runs]),
                "p95": median([r["p95"] for r in runs]),
                "p99": median([r["p99"] for r in runs]),
            }
            scenario_medians[scenario] = med
            ok_sum = sum(r["ok"] for r in runs)
            fail_sum = sum(r["fail"] for r in runs)
            total_ok += ok_sum
            total_req += ok_sum + fail_sum

            lines.append(f'gateway_arena_p50_seconds{{gateway="{name}",scenario="{scenario}"}} {med["p50"]:.6f}')
            lines.append(f'gateway_arena_p95_seconds{{gateway="{name}",scenario="{scenario}"}} {med["p95"]:.6f}')
            lines.append(f'gateway_arena_p99_seconds{{gateway="{name}",scenario="{scenario}"}} {med["p99"]:.6f}')
            lines.append(f'gateway_arena_requests_total{{gateway="{name}",scenario="{scenario}",status="200"}} {ok_sum}')
            if fail_sum > 0:
                lines.append(f'gateway_arena_requests_total{{gateway="{name}",scenario="{scenario}",status="error"}} {fail_sum}')

        # Composite score (median)
        score = compute_gateway_score(scenario_medians, total_ok, total_req)

        # Per-run scores for stddev + CI95
        run_scores = []
        for i, run in enumerate(valid_runs):
            run_medians = {}
            for scenario in SCENARIOS:
                rd = scenario_run_data[scenario][i]
                run_medians[scenario] = rd
            rs = compute_gateway_score(run_medians, total_ok, total_req)
            run_scores.append(rs)

        # Stddev
        if n > 1:
            mean_score = sum(run_scores) / n
            variance = sum((s - mean_score) ** 2 for s in run_scores) / (n - 1)
            stddev = math.sqrt(max(0, variance))
            stderr = stddev / math.sqrt(n)
            t_val = t_critical(n - 1)
            ci_lower = max(0, mean_score - t_val * stderr)
            ci_upper = min(100, mean_score + t_val * stderr)
        else:
            stddev = 0.0
            ci_lower = score
            ci_upper = score

        # Health availability
        health_runs = scenario_run_data["health"]
        h_ok = sum(r["ok"] for r in health_runs)
        h_total = h_ok + sum(r["fail"] for r in health_runs)
        avail = h_ok / h_total if h_total > 0 else 0.0

        lines.append(f'gateway_arena_score{{gateway="{name}"}} {score:.2f}')
        lines.append(f'gateway_arena_availability{{gateway="{name}"}} {avail:.4f}')
        lines.append(f'gateway_arena_score_stddev{{gateway="{name}"}} {stddev:.4f}')
        lines.append(f'gateway_arena_score_ci_lower{{gateway="{name}"}} {ci_lower:.2f}')
        lines.append(f'gateway_arena_score_ci_upper{{gateway="{name}"}} {ci_upper:.2f}')
        lines.append(f'gateway_arena_runs{{gateway="{name}"}} {n}')

        leaderboard.append({"gateway": name, "score": round(score, 2), "stddev": round(stddev, 4),
                            "ci95": f"[{ci_lower:.2f}, {ci_upper:.2f}]"})

        print(f'{{"gateway":"{name}","score":{score:.2f},"stddev":{stddev:.4f},"ci95":[{ci_lower:.2f},{ci_upper:.2f}]}}',
              file=sys.stderr)

    # Output metrics to stdout
    print("\n".join(lines))

    # Leaderboard to stderr
    leaderboard.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({"event": "leaderboard", "ranking": leaderboard}), file=sys.stderr)


if __name__ == "__main__":
    main()
