"""L1 Scorer — Split L1-A (Gateway Core) / L1-B (AI-Native).

Refactors the existing enterprise scorer to produce two separate sub-scores:
- L1-A: 8 dimensions comparable across all gateways
- L1-B: 12 AI-native dimensions (STOA differentiator)
- Composite: 0.4 * L1-A + 0.6 * L1-B

This module is meant to replace the relevant scoring section in
scripts/traffic/arena/run-arena-enterprise.py while maintaining
backward compatibility with existing Prometheus metrics.

Usage:
    from scoring.l1_scorer import score_l1

    result = score_l1(dimensions)
    # result = {
    #   "l1a_core_score": 92.3,
    #   "l1b_ai_score": 95.4,
    #   "composite_score": 94.2,
    #   "dimensions": {...},
    #   "weak_spots": [...]
    # }
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Dimension definitions with L1-A / L1-B classification
# ---------------------------------------------------------------------------

L1A_CORE_DIMENSIONS = {
    "auth_chain":        {"weight": 0.14, "latency_cap": 1.0},
    "policy_eval":       {"weight": 0.12, "latency_cap": 0.2},
    "guardrails":        {"weight": 0.12, "latency_cap": 0.5},
    "quota_burst":       {"weight": 0.12, "latency_cap": 0.5},
    "resilience":        {"weight": 0.14, "latency_cap": 2.0},
    "governance":        {"weight": 0.10, "latency_cap": 1.0},
    "tls_mtls":          {"weight": 0.14, "latency_cap": 0.1},
    "request_transform": {"weight": 0.12, "latency_cap": 0.5},
}

L1B_AI_DIMENSIONS = {
    "mcp_discovery":      {"weight": 0.12, "latency_cap": 0.2},
    "mcp_toolcall":       {"weight": 0.14, "latency_cap": 0.5},
    "llm_routing":        {"weight": 0.10, "latency_cap": 2.0},
    "llm_cost":           {"weight": 0.08, "latency_cap": 1.0},
    "llm_circuit_breaker":{"weight": 0.08, "latency_cap": 2.0},
    "native_tools_crud":  {"weight": 0.08, "latency_cap": 0.5},
    "api_bridge":         {"weight": 0.08, "latency_cap": 2.0},
    "uac_binding":        {"weight": 0.08, "latency_cap": 2.0},
    "pii_detection":      {"weight": 0.06, "latency_cap": 0.5},
    "distributed_tracing":{"weight": 0.06, "latency_cap": 1.0},
    "prompt_cache":       {"weight": 0.06, "latency_cap": 1.0},
    "federation":         {"weight": 0.06, "latency_cap": 2.0},
}

# Verify weights sum to ~1.0
assert abs(sum(d["weight"] for d in L1A_CORE_DIMENSIONS.values()) - 1.0) < 0.01
assert abs(sum(d["weight"] for d in L1B_AI_DIMENSIONS.values()) - 1.0) < 0.01

# Composite weighting: AI-readiness is the differentiator
L1A_COMPOSITE_WEIGHT = 0.4
L1B_COMPOSITE_WEIGHT = 0.6


@dataclass
class DimensionResult:
    name: str
    group: str  # "L1-A" or "L1-B"
    availability_score: float  # 0-100
    latency_score: float  # 0-100
    score: float  # 0-100 (0.6*avail + 0.4*latency)
    weight: float
    p95_ms: float
    passes: int
    fails: int
    supported: bool


def score_dimension(
    name: str,
    passes: int,
    fails: int,
    p95_seconds: float,
    latency_cap: float,
    weight: float,
    group: str,
    supported: bool = True,
) -> DimensionResult:
    """Score a single dimension using the standard formula."""
    if not supported or (passes + fails) == 0:
        return DimensionResult(
            name=name, group=group,
            availability_score=0, latency_score=0, score=0,
            weight=weight, p95_ms=0, passes=0, fails=0, supported=False,
        )

    availability = (passes / (passes + fails)) * 100
    latency_score = max(0, 100 * (1 - p95_seconds / latency_cap))
    score = 0.6 * availability + 0.4 * latency_score

    return DimensionResult(
        name=name, group=group,
        availability_score=round(availability, 1),
        latency_score=round(latency_score, 1),
        score=round(score, 1),
        weight=weight,
        p95_ms=round(p95_seconds * 1000, 1),
        passes=passes, fails=fails, supported=True,
    )


def score_l1(
    dimensions: dict[str, dict],
    features: list[str] | None = None,
) -> dict:
    """Compute L1-A, L1-B, and composite scores.

    Args:
        dimensions: dict mapping dimension name to
            {"passes": int, "fails": int, "p95_seconds": float}
        features: list of supported features for the gateway (optional).
            Dimensions not in this list score 0.

    Returns:
        dict with l1a_core_score, l1b_ai_score, composite_score,
        dimensions detail, and weak_spots.
    """
    features_set = set(features) if features else None

    results: list[DimensionResult] = []

    # Score L1-A dimensions
    for dim_name, dim_cfg in L1A_CORE_DIMENSIONS.items():
        data = dimensions.get(dim_name, {})
        supported = features_set is None or dim_name in features_set
        r = score_dimension(
            name=dim_name,
            passes=data.get("passes", 0),
            fails=data.get("fails", 0),
            p95_seconds=data.get("p95_seconds", 0),
            latency_cap=dim_cfg["latency_cap"],
            weight=dim_cfg["weight"],
            group="L1-A",
            supported=supported and (data.get("passes", 0) + data.get("fails", 0)) > 0,
        )
        results.append(r)

    # Score L1-B dimensions
    for dim_name, dim_cfg in L1B_AI_DIMENSIONS.items():
        data = dimensions.get(dim_name, {})
        supported = features_set is None or dim_name in features_set
        r = score_dimension(
            name=dim_name,
            passes=data.get("passes", 0),
            fails=data.get("fails", 0),
            p95_seconds=data.get("p95_seconds", 0),
            latency_cap=dim_cfg["latency_cap"],
            weight=dim_cfg["weight"],
            group="L1-B",
            supported=supported and (data.get("passes", 0) + data.get("fails", 0)) > 0,
        )
        results.append(r)

    # Compute sub-scores
    l1a_results = [r for r in results if r.group == "L1-A"]
    l1b_results = [r for r in results if r.group == "L1-B"]

    l1a_score = sum(r.score * r.weight for r in l1a_results)
    l1b_score = sum(r.score * r.weight for r in l1b_results)
    composite = L1A_COMPOSITE_WEIGHT * l1a_score + L1B_COMPOSITE_WEIGHT * l1b_score

    # Identify weak spots (score < 70)
    weak_spots = [
        f"{r.name}: {r.score}"
        for r in sorted(results, key=lambda x: x.score)
        if r.supported and r.score < 70
    ]

    return {
        "l1a_core_score": round(l1a_score, 1),
        "l1b_ai_score": round(l1b_score, 1),
        "composite_score": round(composite, 1),
        "dimensions": {
            r.name: {
                "group": r.group,
                "score": r.score,
                "availability": r.availability_score,
                "latency_score": r.latency_score,
                "p95_ms": r.p95_ms,
                "supported": r.supported,
            }
            for r in results
        },
        "weak_spots": weak_spots,
    }
