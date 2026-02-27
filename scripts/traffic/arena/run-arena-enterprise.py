#!/usr/bin/env python3
"""Arena Enterprise Score Aggregator — Layer 1: Enterprise AI Readiness.

Computes per-dimension scores and a composite Enterprise Readiness Index
from k6 enterprise benchmark summaries.

Gateways without MCP (mcp_base == null) score 0 on MCP dimensions.
The spec is open — any gateway can implement MCP and re-run.

Uses stdlib only (no scipy/numpy).

Usage:
  python3 run-arena-enterprise.py <work_dir> <gateways_json>
"""

import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# t-distribution critical values for 95% CI (two-tailed, alpha=0.05)
T_TABLE = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
}

# 8 Enterprise dimensions with weights
DIMENSIONS = [
    {"key": "mcp_discovery",  "scenario": "ent_mcp_discovery",  "weight": 0.15, "requires_mcp": True},
    {"key": "mcp_toolcall",   "scenario": "ent_mcp_toolcall",   "weight": 0.20, "requires_mcp": True},
    {"key": "auth_chain",     "scenario": "ent_auth_chain",     "weight": 0.15, "requires_mcp": True},
    {"key": "policy_eval",    "scenario": "ent_policy_eval",    "weight": 0.15, "requires_mcp": True},
    {"key": "guardrails",     "scenario": "ent_guardrails",     "weight": 0.10, "requires_mcp": True},
    {"key": "quota_burst",    "scenario": "ent_quota_burst",    "weight": 0.10, "requires_mcp": False},
    {"key": "resilience",     "scenario": "ent_resilience",     "weight": 0.10, "requires_mcp": True},
    {"key": "governance",     "scenario": "ent_governance",     "weight": 0.05, "requires_mcp": False},
]

# Latency caps per dimension (seconds) — p95 above this = score 0
LATENCY_CAPS = {
    "mcp_discovery": 0.5,    # 500ms
    "mcp_toolcall": 0.5,     # 500ms
    "auth_chain": 1.0,       # 1s
    "policy_eval": 0.2,      # 200ms overhead cap
    "guardrails": 1.0,       # 1s
    "quota_burst": 1.0,      # 1s
    "resilience": 1.0,       # 1s
    "governance": 2.0,       # 2s (admin endpoints, less critical)
}


def t_critical(df: int) -> float:
    """Look up t-critical value for given degrees of freedom."""
    if df in T_TABLE:
        return T_TABLE[df]
    keys = sorted(T_TABLE.keys())
    for k in keys:
        if k >= df:
            return T_TABLE[k]
    return 1.96


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
    return mean, max(0, mean - t_val * stderr), min(100, mean + t_val * stderr)


def median(values: list[float]) -> float:
    """Compute median of a list."""
    if not values:
        return 0.0
    s = sorted(values)
    return s[len(s) // 2]


def extract_checks(json_path: Path) -> dict[str, int]:
    """Extract check pass/fail counts from k6 JSON summary."""
    if not json_path.exists():
        return {"passes": 0, "fails": 0}
    try:
        data = json.loads(json_path.read_text())
        checks = data.get("metrics", {}).get("checks", {}).get("values", {})
        return {
            "passes": int(checks.get("passes", 0)),
            "fails": int(checks.get("fails", 0)),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {"passes": 0, "fails": 0}


def extract_latency(json_path: Path) -> dict[str, float]:
    """Extract latency percentiles from k6 JSON summary (returns seconds)."""
    if not json_path.exists():
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    try:
        data = json.loads(json_path.read_text())
        vals = data.get("metrics", {}).get("http_req_duration", {}).get("values", {})
        return {
            "p50": vals.get("p(50)", 0) / 1000.0,
            "p95": vals.get("p(95)", 0) / 1000.0,
            "p99": vals.get("p(99)", 0) / 1000.0,
        }
    except (json.JSONDecodeError, KeyError):
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}


def score_dimension(dim_key: str, checks: dict[str, int], latency: dict[str, float]) -> float:
    """Score a single dimension (0-100).

    Scoring formula:
      availability_score = passes / (passes + fails) * 100
      latency_score = max(0, 100 * (1 - p95 / cap))
      dimension_score = 0.6 * availability_score + 0.4 * latency_score

    If no requests were made (gateway doesn't support the feature): score = 0.
    """
    total = checks["passes"] + checks["fails"]
    if total == 0:
        return 0.0

    avail_score = 100.0 * checks["passes"] / total
    cap = LATENCY_CAPS.get(dim_key, 1.0)
    lat_score = max(0.0, min(100.0, 100.0 * (1.0 - latency["p95"] / cap)))

    return max(0.0, min(100.0, 0.6 * avail_score + 0.4 * lat_score))


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <work_dir> <gateways_json>", file=sys.stderr)
        sys.exit(1)

    work_dir = Path(sys.argv[1])
    gateways = json.loads(sys.argv[2])
    discard_first = int(os.environ.get("DISCARD_FIRST", "1"))
    total_runs = int(os.environ.get("RUNS", "3"))

    # Prometheus metric families
    families: dict[str, list[str]] = {
        "gateway_arena_enterprise_score": [],
        "gateway_arena_enterprise_dimension": [],
        "gateway_arena_enterprise_score_ci_lower": [],
        "gateway_arena_enterprise_score_ci_upper": [],
        "gateway_arena_enterprise_score_stddev": [],
        "gateway_arena_enterprise_runs": [],
        "gateway_arena_enterprise_latency_p95": [],
    }
    family_meta = {
        "gateway_arena_enterprise_score": ("gauge", "Enterprise AI Readiness Index 0-100"),
        "gateway_arena_enterprise_dimension": ("gauge", "Per-dimension enterprise score 0-100"),
        "gateway_arena_enterprise_score_ci_lower": ("gauge", "Enterprise score CI95 lower bound"),
        "gateway_arena_enterprise_score_ci_upper": ("gauge", "Enterprise score CI95 upper bound"),
        "gateway_arena_enterprise_score_stddev": ("gauge", "Enterprise score run-to-run stddev"),
        "gateway_arena_enterprise_runs": ("gauge", "Number of valid enterprise runs"),
        "gateway_arena_enterprise_latency_p95": ("gauge", "P95 latency per enterprise dimension"),
    }

    leaderboard = []

    for gw in gateways:
        name = gw["name"]
        has_mcp = bool(gw.get("mcp_base"))
        gw_dir = work_dir / name
        valid_runs = list(range(discard_first + 1, total_runs + 1))
        n = len(valid_runs)

        # Per-dimension, per-run scores
        dim_run_scores: dict[str, list[float]] = {d["key"]: [] for d in DIMENSIONS}
        dim_median_latencies: dict[str, float] = {}

        for dim in DIMENSIONS:
            dim_key = dim["key"]
            scenario = dim["scenario"]

            # Gateway without MCP scores 0 on MCP dimensions
            if dim["requires_mcp"] and not has_mcp:
                dim_run_scores[dim_key] = [0.0] * n
                dim_median_latencies[dim_key] = 0.0
                continue

            run_latencies: list[float] = []

            for run in valid_runs:
                jf = gw_dir / f"run-{run}" / f"{scenario}.json"
                checks = extract_checks(jf)
                latency = extract_latency(jf)
                s = score_dimension(dim_key, checks, latency)
                dim_run_scores[dim_key].append(s)
                run_latencies.append(latency["p95"])

            dim_median_latencies[dim_key] = median(run_latencies)

        # Compute per-run composite scores
        run_composites: list[float] = []
        for i in range(n):
            composite = 0.0
            for dim in DIMENSIONS:
                scores = dim_run_scores[dim["key"]]
                composite += dim["weight"] * (scores[i] if i < len(scores) else 0.0)
            run_composites.append(max(0.0, min(100.0, composite)))

        # Median composite score
        enterprise_score = median(run_composites)

        # CI95 on composite
        if n > 1:
            mean_score = sum(run_composites) / n
            variance = sum((s - mean_score) ** 2 for s in run_composites) / (n - 1)
            stddev = math.sqrt(max(0, variance))
            _, ci_lower, ci_upper = t_ci95(run_composites)
        else:
            stddev = 0.0
            ci_lower = enterprise_score
            ci_upper = enterprise_score

        # Emit Prometheus metrics
        families["gateway_arena_enterprise_score"].append(
            f'gateway_arena_enterprise_score{{gateway="{name}"}} {enterprise_score:.2f}')
        families["gateway_arena_enterprise_score_ci_lower"].append(
            f'gateway_arena_enterprise_score_ci_lower{{gateway="{name}"}} {ci_lower:.2f}')
        families["gateway_arena_enterprise_score_ci_upper"].append(
            f'gateway_arena_enterprise_score_ci_upper{{gateway="{name}"}} {ci_upper:.2f}')
        families["gateway_arena_enterprise_score_stddev"].append(
            f'gateway_arena_enterprise_score_stddev{{gateway="{name}"}} {stddev:.4f}')
        families["gateway_arena_enterprise_runs"].append(
            f'gateway_arena_enterprise_runs{{gateway="{name}"}} {n}')

        # Per-dimension metrics
        dim_details = {}
        for dim in DIMENSIONS:
            dim_key = dim["key"]
            dim_scores = dim_run_scores[dim_key]
            dim_score = median(dim_scores)
            dim_details[dim_key] = round(dim_score, 1)
            families["gateway_arena_enterprise_dimension"].append(
                f'gateway_arena_enterprise_dimension{{gateway="{name}",dimension="{dim_key}"}} {dim_score:.2f}')
            families["gateway_arena_enterprise_latency_p95"].append(
                f'gateway_arena_enterprise_latency_p95{{gateway="{name}",dimension="{dim_key}"}} {dim_median_latencies[dim_key]:.6f}')

        leaderboard.append({
            "gateway": name,
            "enterprise_score": round(enterprise_score, 2),
            "stddev": round(stddev, 4),
            "ci95": f"[{ci_lower:.2f}, {ci_upper:.2f}]",
            "dimensions": dim_details,
        })

        print(
            f'{{"gateway":"{name}","enterprise_score":{enterprise_score:.2f},'
            f'"stddev":{stddev:.4f},"ci95":[{ci_lower:.2f},{ci_upper:.2f}],'
            f'"dimensions":{json.dumps(dim_details)}}}',
            file=sys.stderr,
        )

    # Output Prometheus metrics grouped by family
    lines = []
    for family_name, samples in families.items():
        if not samples:
            continue
        mtype, mhelp = family_meta[family_name]
        lines.append(f"# HELP {family_name} {mhelp}")
        lines.append(f"# TYPE {family_name} {mtype}")
        lines.extend(samples)
    print("\n".join(lines))

    # Leaderboard to stderr
    leaderboard.sort(key=lambda x: x["enterprise_score"], reverse=True)
    print(json.dumps({"event": "enterprise_leaderboard", "ranking": leaderboard}), file=sys.stderr)

    # Export to OpenSearch for long-term retention (CAB-1558)
    export_to_opensearch(leaderboard)


def export_to_opensearch(leaderboard: list[dict]) -> None:
    """Export arena scores to OpenSearch for long-term retention.

    Each run creates one document per gateway in the 'arena-scores' index.
    Uses stdlib urllib only (no requests/httpx dependency).
    Env vars:
      OPENSEARCH_URL — OpenSearch base URL (default: http://opensearch.stoa-system.svc:9200)
      OPENSEARCH_ENABLED — set to "false" to skip export (default: true)
    """
    if os.environ.get("OPENSEARCH_ENABLED", "true").lower() == "false":
        return

    base_url = os.environ.get(
        "OPENSEARCH_URL", "http://opensearch.stoa-system.svc:9200"
    )
    index = "arena-scores"
    timestamp = datetime.now(timezone.utc).isoformat()

    for entry in leaderboard:
        doc = {
            "@timestamp": timestamp,
            "layer": "enterprise",
            "gateway": entry["gateway"],
            "enterprise_score": entry["enterprise_score"],
            "stddev": entry["stddev"],
            "ci95_lower": float(entry["ci95"].strip("[]").split(",")[0]),
            "ci95_upper": float(entry["ci95"].strip("[]").split(",")[1]),
            "dimensions": entry["dimensions"],
        }
        try:
            payload = json.dumps(doc).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/{index}/_doc",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:
            print(
                f'{{"opensearch_export_error":"{entry["gateway"]}","{e}"}}',
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
