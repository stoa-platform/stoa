"""Deterministic scorer for phase05-harness.

Inputs:
  --prompts  prompts.jsonl    (ground truth)
  --runs     runs.jsonl       (one line per prompt x model x condition x run)

Output (stdout): report.json with per (model, condition) aggregates and binary
GREEN/RED verdict per variant following the contract in README.md.

No LLM-as-judge. No random sampling outside the fixed-seed bootstrap.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

BOOTSTRAP_ITERS = 10_000
BOOTSTRAP_SEED = 20260419
ACC_GATE = 0.10  # +10 pts absolute
REGRESSION_GATE = 0.20  # +20% max on cost/latency
SCALABILITY_GATE = 0.90  # acc@200 >= 0.9 * acc@50
TARGET_MODEL = "claude-sonnet-4-6"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _scored(run: dict[str, Any], truth: dict[str, Any]) -> int:
    """1 if top-1 match, else 0. Applies per-condition tool-name rules."""
    condition = run["condition"]
    called = run.get("tool_call")
    gt = truth["ground_truth"]
    expect_refusal = gt.get("op_id") is None

    if expect_refusal:
        return 1 if called is None else 0
    if called is None:
        return 0

    tool_name = called.get("tool_name", "")
    action = (called.get("input") or {}).get("action")

    if condition == "per-op":
        expected = f"{truth['tenant']}-{truth['api']}-{gt['op_id']}"
        return 1 if tool_name == expected else 0

    expected_tool = f"{truth['tenant']}:{truth['api']}"
    return 1 if tool_name == expected_tool and action == gt["op_id"] else 0


def _bootstrap_ci(diffs: list[int], iters: int = BOOTSTRAP_ITERS) -> tuple[float, float]:
    if not diffs:
        return 0.0, 0.0
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(diffs)
    means: list[float] = []
    for _ in range(iters):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[int(0.975 * iters)]
    return lo, hi


def _percentile(xs: list[float], pct: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]


def _aggregate(
    prompts: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    by_prompt = {p["id"]: p for p in prompts}
    # key = (model, condition) -> list of (prompt_id, score, cost, latency)
    bucket: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    # For scalability: key = (model, condition, scale) -> list
    scale_bucket: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)

    for r in runs:
        gt = by_prompt.get(r["prompt_id"])
        if gt is None:
            continue
        s = _scored(r, gt)
        cost = r.get("tokens_in", 0) + r.get("tokens_out", 0)
        latency = r.get("latency_ms", 0.0)
        item = {"prompt_id": r["prompt_id"], "score": s, "cost": cost, "latency": latency, "category": gt.get("category", "normal")}
        bucket[(r["model"], r["condition"])].append(item)
        if r.get("scale") is not None:
            scale_bucket[(r["model"], r["condition"], int(r["scale"]))].append(item)

    per_cell: dict[str, dict[str, Any]] = {}
    for (model, cond), items in sorted(bucket.items()):
        scores = [it["score"] for it in items]
        acc = sum(scores) / len(scores) if scores else 0.0
        acc_by_cat: dict[str, float] = {}
        for cat in ("normal", "distractor", "no_valid_tool"):
            cat_scores = [it["score"] for it in items if it["category"] == cat]
            acc_by_cat[cat] = (sum(cat_scores) / len(cat_scores)) if cat_scores else None  # type: ignore[assignment]
        per_cell[f"{model}|{cond}"] = {
            "model": model,
            "condition": cond,
            "n": len(items),
            "top1_accuracy": acc,
            "top1_accuracy_by_category": acc_by_cat,
            "median_cost_tokens": statistics.median([it["cost"] for it in items]) if items else 0,
            "latency_p95_ms": _percentile([it["latency"] for it in items], 95),
        }
    return {"per_cell": per_cell, "buckets": bucket, "scale": scale_bucket}


def _paired_diff(
    bucket: dict[tuple[str, str], list[dict[str, Any]]],
    model: str,
    variant: str,
) -> list[int]:
    """Paired per-prompt score diff between variant and coarse for one model."""
    variant_items = {it["prompt_id"]: it["score"] for it in bucket.get((model, variant), [])}
    coarse_items = {it["prompt_id"]: it["score"] for it in bucket.get((model, "coarse"), [])}
    common = sorted(set(variant_items) & set(coarse_items))
    return [variant_items[p] - coarse_items[p] for p in common]


def _verdict_for_variant(
    agg: dict[str, Any],
    variant: str,
) -> dict[str, Any]:
    """Apply the frozen decision rule for one variant. Binary GREEN/RED."""
    per_cell = agg["per_cell"]
    bucket = agg["buckets"]
    scale_bucket = agg["scale"]

    models = sorted({m for (m, c) in bucket.keys()})
    per_model: dict[str, dict[str, Any]] = {}

    for model in models:
        cell_v = per_cell.get(f"{model}|{variant}")
        cell_c = per_cell.get(f"{model}|coarse")
        if not cell_v or not cell_c:
            per_model[model] = {"green": False, "reason": "missing cell"}
            continue

        diffs = _paired_diff(bucket, model, variant)
        mean_gain = sum(diffs) / len(diffs) if diffs else 0.0
        ci_lo, ci_hi = _bootstrap_ci(diffs)

        cost_regression = (
            cell_v["median_cost_tokens"] / cell_c["median_cost_tokens"] - 1
            if cell_c["median_cost_tokens"] > 0 else 0.0
        )
        latency_regression = (
            cell_v["latency_p95_ms"] / cell_c["latency_p95_ms"] - 1
            if cell_c["latency_p95_ms"] > 0 else 0.0
        )

        checks: dict[str, Any] = {
            "gain_10pts": mean_gain >= ACC_GATE,
            "ci95_lower_positive": ci_lo > 0,
            "cost_not_regressed": cost_regression < REGRESSION_GATE,
            "latency_not_regressed": latency_regression < REGRESSION_GATE,
        }
        if variant == "per-op":
            acc50 = _scale_acc(scale_bucket, model, "per-op", 50)
            acc200 = _scale_acc(scale_bucket, model, "per-op", 200)
            if acc50 is not None and acc200 is not None and acc50 > 0:
                checks["scalability"] = (acc200 / acc50) >= SCALABILITY_GATE
            else:
                checks["scalability"] = None  # not run

        all_bool = [v for v in checks.values() if isinstance(v, bool)]
        is_green = bool(all_bool) and all(all_bool)
        per_model[model] = {
            "green": is_green,
            "mean_gain": mean_gain,
            "ci95": [ci_lo, ci_hi],
            "cost_regression": cost_regression,
            "latency_regression": latency_regression,
            "checks": checks,
            "n_paired": len(diffs),
        }

    target_green = per_model.get(TARGET_MODEL, {}).get("green", False)
    other_green = any(m != TARGET_MODEL and per_model[m].get("green") for m in per_model)
    verdict = "GREEN" if (target_green and other_green) else "RED"
    return {
        "variant": variant,
        "verdict": verdict,
        "target_model": TARGET_MODEL,
        "target_model_green": target_green,
        "any_other_green": other_green,
        "per_model": per_model,
    }


def _scale_acc(
    scale_bucket: dict[tuple[str, str, int], list[dict[str, Any]]],
    model: str,
    condition: str,
    scale: int,
) -> float | None:
    items = scale_bucket.get((model, condition, scale))
    if not items:
        return None
    return sum(it["score"] for it in items) / len(items)


def score(prompts_path: Path, runs_path: Path) -> dict[str, Any]:
    prompts = _load_jsonl(prompts_path)
    runs = _load_jsonl(runs_path)
    agg = _aggregate(prompts, runs)
    verdicts = {
        "per-op": _verdict_for_variant(agg, "per-op"),
        "enriched-single": _verdict_for_variant(agg, "enriched-single"),
    }
    return {
        "per_cell": agg["per_cell"],
        "verdicts": verdicts,
        "config": {
            "bootstrap_iters": BOOTSTRAP_ITERS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "acc_gate": ACC_GATE,
            "regression_gate": REGRESSION_GATE,
            "scalability_gate": SCALABILITY_GATE,
            "target_model": TARGET_MODEL,
        },
    }


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", required=True, type=Path)
    ap.add_argument("--runs", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    report = score(args.prompts, args.runs)
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.out:
        args.out.write_text(payload)
    print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
