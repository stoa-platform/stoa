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

# Weights (updated for ramp_up scenario)
W_BASE = 0.10
W_BURST50 = 0.20
W_BURST100 = 0.20
W_AVAIL = 0.15
W_ERROR = 0.10
W_CONSIST = 0.10
W_RAMP = 0.15

SCENARIOS = ["health", "sequential", "burst_10", "burst_50", "burst_100", "sustained", "ramp_up"]


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


def t_ci95(values: list[float]) -> tuple[float, float, float]:
    """Compute mean and CI95 bounds for a list of values."""
    n = len(values)
    if n < 2:
        v = values[0] if values else 0.0
        return v, v, v
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    stddev = math.sqrt(max(0, variance))
    stderr = stddev / math.sqrt(n)
    t_val = t_critical(n - 1)
    return mean, max(0, mean - t_val * stderr), mean + t_val * stderr


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


def extract_ramp_metrics(json_path: Path) -> dict:
    """Extract ramp-up throughput metrics from k6 JSON summary."""
    if not json_path.exists():
        return {"rate": 0.0, "success_rate": 1.0, "p99": 0.0}
    try:
        data = json.loads(json_path.read_text())
        metrics = data.get("metrics", {})
        rate = metrics.get("http_reqs", {}).get("values", {}).get("rate", 0.0)
        p99 = metrics.get("http_req_duration", {}).get("values", {}).get("p(99)", 0.0) / 1000.0
        checks = metrics.get("checks", {}).get("values", {})
        passes = checks.get("passes", 0)
        fails = checks.get("fails", 0)
        total = passes + fails
        success_rate = passes / total if total > 0 else 1.0
        return {"rate": rate, "success_rate": success_rate, "p99": p99}
    except (json.JSONDecodeError, KeyError, ValueError, ZeroDivisionError):
        return {"rate": 0.0, "success_rate": 1.0, "p99": 0.0}


def ramp_score(rate: float, success_rate: float, p99: float) -> float:
    """Score ramp-up: effective throughput capped at 100 req/s.

    effective_rate = rate * success_rate, with penalty if p99 > 2s.
    Score = min(100, effective_rate).
    """
    effective = rate * success_rate
    if p99 > 2.0:
        effective *= max(0.5, 1.0 - (p99 - 2.0) / 8.0)
    return max(0.0, min(100.0, effective))


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


def compute_gateway_score(scenario_medians: dict, total_ok: int, total_req: int,
                          ramp_val: float = 0.0) -> float:
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

    score = (W_BASE * base + W_BURST50 * b50 + W_BURST100 * b100 +
             W_AVAIL * avail + W_ERROR * error + W_CONSIST * consist +
             W_RAMP * ramp_val)
    return max(0.0, min(100.0, score))


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <work_dir> <gateways_json>", file=sys.stderr)
        sys.exit(1)

    work_dir = Path(sys.argv[1])
    gateways = json.loads(sys.argv[2])
    discard_first = int(os.environ.get("DISCARD_FIRST", "1"))
    total_runs = int(os.environ.get("RUNS", "5"))

    # Prometheus text format requires all samples of a metric family grouped together.
    # Collect samples per metric family, emit grouped at the end.
    families: dict[str, list[str]] = {
        "gateway_arena_score": [],
        "gateway_arena_availability": [],
        "gateway_arena_score_stddev": [],
        "gateway_arena_score_ci_lower": [],
        "gateway_arena_score_ci_upper": [],
        "gateway_arena_runs": [],
        "gateway_arena_p50_seconds": [],
        "gateway_arena_p95_seconds": [],
        "gateway_arena_p99_seconds": [],
        "gateway_arena_p50_ci_lower_seconds": [],
        "gateway_arena_p50_ci_upper_seconds": [],
        "gateway_arena_p95_ci_lower_seconds": [],
        "gateway_arena_p95_ci_upper_seconds": [],
        "gateway_arena_p99_ci_lower_seconds": [],
        "gateway_arena_p99_ci_upper_seconds": [],
        "gateway_arena_ramp_rate": [],
        "gateway_arena_requests_total": [],
    }
    family_meta = {
        "gateway_arena_score": ("gauge", "Composite arena score 0-100"),
        "gateway_arena_availability": ("gauge", "Gateway availability 0-1"),
        "gateway_arena_score_stddev": ("gauge", "Run-to-run standard deviation"),
        "gateway_arena_score_ci_lower": ("gauge", "CI95 lower bound"),
        "gateway_arena_score_ci_upper": ("gauge", "CI95 upper bound"),
        "gateway_arena_runs": ("gauge", "Number of valid runs after discard"),
        "gateway_arena_p50_seconds": ("gauge", "P50 latency"),
        "gateway_arena_p95_seconds": ("gauge", "P95 latency"),
        "gateway_arena_p99_seconds": ("gauge", "P99 latency"),
        "gateway_arena_p50_ci_lower_seconds": ("gauge", "P50 latency CI95 lower bound"),
        "gateway_arena_p50_ci_upper_seconds": ("gauge", "P50 latency CI95 upper bound"),
        "gateway_arena_p95_ci_lower_seconds": ("gauge", "P95 latency CI95 lower bound"),
        "gateway_arena_p95_ci_upper_seconds": ("gauge", "P95 latency CI95 upper bound"),
        "gateway_arena_p99_ci_lower_seconds": ("gauge", "P99 latency CI95 lower bound"),
        "gateway_arena_p99_ci_upper_seconds": ("gauge", "P99 latency CI95 upper bound"),
        "gateway_arena_ramp_rate": ("gauge", "Ramp-up max sustained req/s"),
        "gateway_arena_requests_total": ("gauge", "Total requests by status"),
    }

    leaderboard = []

    for gw in gateways:
        name = gw["name"]
        gw_dir = work_dir / name
        valid_runs = list(range(discard_first + 1, total_runs + 1))
        n = len(valid_runs)

        # Collect per-scenario per-run data
        scenario_run_data: dict[str, list[dict]] = {s: [] for s in SCENARIOS}
        ramp_run_data: list[dict] = []

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
            # Ramp-up specific metrics
            ramp_jf = gw_dir / f"run-{run}" / "ramp_up.json"
            ramp_run_data.append(extract_ramp_metrics(ramp_jf))

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

            families["gateway_arena_p50_seconds"].append(
                f'gateway_arena_p50_seconds{{gateway="{name}",scenario="{scenario}"}} {med["p50"]:.6f}')
            families["gateway_arena_p95_seconds"].append(
                f'gateway_arena_p95_seconds{{gateway="{name}",scenario="{scenario}"}} {med["p95"]:.6f}')
            families["gateway_arena_p99_seconds"].append(
                f'gateway_arena_p99_seconds{{gateway="{name}",scenario="{scenario}"}} {med["p99"]:.6f}')
            families["gateway_arena_requests_total"].append(
                f'gateway_arena_requests_total{{gateway="{name}",scenario="{scenario}",status="200"}} {ok_sum}')
            if fail_sum > 0:
                families["gateway_arena_requests_total"].append(
                    f'gateway_arena_requests_total{{gateway="{name}",scenario="{scenario}",status="error"}} {fail_sum}')

            # CI95 per-scenario latency
            p50_vals = [r["p50"] for r in runs]
            p95_vals = [r["p95"] for r in runs]
            p99_vals = [r["p99"] for r in runs]
            _, p50_lo, p50_hi = t_ci95(p50_vals)
            _, p95_lo, p95_hi = t_ci95(p95_vals)
            _, p99_lo, p99_hi = t_ci95(p99_vals)
            families["gateway_arena_p50_ci_lower_seconds"].append(
                f'gateway_arena_p50_ci_lower_seconds{{gateway="{name}",scenario="{scenario}"}} {p50_lo:.6f}')
            families["gateway_arena_p50_ci_upper_seconds"].append(
                f'gateway_arena_p50_ci_upper_seconds{{gateway="{name}",scenario="{scenario}"}} {p50_hi:.6f}')
            families["gateway_arena_p95_ci_lower_seconds"].append(
                f'gateway_arena_p95_ci_lower_seconds{{gateway="{name}",scenario="{scenario}"}} {p95_lo:.6f}')
            families["gateway_arena_p95_ci_upper_seconds"].append(
                f'gateway_arena_p95_ci_upper_seconds{{gateway="{name}",scenario="{scenario}"}} {p95_hi:.6f}')
            families["gateway_arena_p99_ci_lower_seconds"].append(
                f'gateway_arena_p99_ci_lower_seconds{{gateway="{name}",scenario="{scenario}"}} {p99_lo:.6f}')
            families["gateway_arena_p99_ci_upper_seconds"].append(
                f'gateway_arena_p99_ci_upper_seconds{{gateway="{name}",scenario="{scenario}"}} {p99_hi:.6f}')

        # Ramp-up scoring: median effective rate across runs
        ramp_scores = [ramp_score(r["rate"], r["success_rate"], r["p99"]) for r in ramp_run_data]
        median_ramp = median(ramp_scores)
        median_rate = median([r["rate"] for r in ramp_run_data])
        families["gateway_arena_ramp_rate"].append(
            f'gateway_arena_ramp_rate{{gateway="{name}"}} {median_rate:.2f}')

        # Composite score (median)
        score = compute_gateway_score(scenario_medians, total_ok, total_req, median_ramp)

        # Per-run scores for stddev + CI95
        run_scores = []
        for i, run in enumerate(valid_runs):
            run_medians = {}
            for scenario in SCENARIOS:
                rd = scenario_run_data[scenario][i]
                run_medians[scenario] = rd
            rs = compute_gateway_score(run_medians, total_ok, total_req, ramp_scores[i])
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

        families["gateway_arena_score"].append(f'gateway_arena_score{{gateway="{name}"}} {score:.2f}')
        families["gateway_arena_availability"].append(f'gateway_arena_availability{{gateway="{name}"}} {avail:.4f}')
        families["gateway_arena_score_stddev"].append(f'gateway_arena_score_stddev{{gateway="{name}"}} {stddev:.4f}')
        families["gateway_arena_score_ci_lower"].append(f'gateway_arena_score_ci_lower{{gateway="{name}"}} {ci_lower:.2f}')
        families["gateway_arena_score_ci_upper"].append(f'gateway_arena_score_ci_upper{{gateway="{name}"}} {ci_upper:.2f}')
        families["gateway_arena_runs"].append(f'gateway_arena_runs{{gateway="{name}"}} {n}')

        leaderboard.append({"gateway": name, "score": round(score, 2), "stddev": round(stddev, 4),
                            "ci95": f"[{ci_lower:.2f}, {ci_upper:.2f}]", "ramp_rate": round(median_rate, 2)})

        print(f'{{"gateway":"{name}","score":{score:.2f},"stddev":{stddev:.4f},"ci95":[{ci_lower:.2f},{ci_upper:.2f}],"ramp_rate":{median_rate:.2f}}}',
              file=sys.stderr)

    # Output metrics to stdout — grouped by metric family (Prometheus requirement)
    lines = []
    for family_name in families:
        if not families[family_name]:
            continue
        mtype, mhelp = family_meta[family_name]
        lines.append(f"# HELP {family_name} {mhelp}")
        lines.append(f"# TYPE {family_name} {mtype}")
        lines.extend(families[family_name])
    print("\n".join(lines))

    # Leaderboard to stderr
    leaderboard.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({"event": "leaderboard", "ranking": leaderboard}), file=sys.stderr)


if __name__ == "__main__":
    main()
