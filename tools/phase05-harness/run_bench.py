"""Bench runner: 3 conditions x 3 models x N prompts x R runs.

Emits a JSONL stream to stdout (or --out). One record per prompt * model *
condition * run index. No scoring here — pipe to `score.py`.

Usage:
    python run_bench.py \\
        --prompts prompts.jsonl \\
        --specs-dir specs \\
        --models claude-opus-4-7 claude-sonnet-4-6 claude-haiku-4-5-20251001 \\
        --conditions coarse per-op enriched-single \\
        --runs 3 \\
        --out runs.jsonl

Environment:
    ANTHROPIC_API_KEY  required unless --dry-run

Dry-run mode emits stub records with uniform top-1 accuracy for pipeline tests.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from build_enriched import build_coarse, build_enriched, build_per_op

SYSTEM_PROMPT = (
    "You are an API router. Call exactly one tool for each user request. "
    "If no tool matches the user's intent, respond with a brief refusal and call nothing. "
    "Never ask clarifying questions. Never call more than one tool."
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _spec_for(api: str, specs_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((specs_dir / f"{api}.yaml").read_text())


def _tools_for_condition(
    condition: str,
    api: str,
    tenant: str,
    spec: dict[str, Any],
    scale: int | None = None,
) -> list[dict[str, Any]]:
    if condition == "coarse":
        return [build_coarse(spec, tenant, api)]
    if condition == "enriched-single":
        return [build_enriched(spec, tenant, api)]
    if condition == "per-op":
        tools = build_per_op(spec, tenant, api)
        if scale is not None:
            tools = _scale_tools(tools, scale)
        return tools
    raise ValueError(f"unknown condition {condition}")


def _scale_tools(tools: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    """Pad (or truncate) a tool list to exactly `target` entries by prefix-dup.

    Ordering is stable, deterministic. Duplicated tools get an `_dupN` suffix.
    """
    if len(tools) >= target:
        return tools[:target]
    out: list[dict[str, Any]] = list(tools)
    base = list(tools)
    dup_idx = 0
    while len(out) < target:
        src = base[dup_idx % len(base)]
        dup = copy.deepcopy(src)
        dup_n = dup_idx // len(base) + 1
        dup["name"] = f"{src['name']}_dup{dup_n}_{dup_idx % len(base)}"
        out.append(dup)
        dup_idx += 1
    return out


def _call_anthropic(
    client: Any,
    model: str,
    tools: list[dict[str, Any]],
    prompt: str,
) -> dict[str, Any]:
    """Returns {tool_call, latency_ms, tokens_in, tokens_out, stop_reason}.

    Transport-layer bijection: Anthropic requires tool names to match
    ^[a-zA-Z0-9_-]{1,128}$, but the canonical coarse/enriched form uses
    `tenant:api` (colon). We substitute `:` -> `__` before the API call
    and reverse-map the response before persistence, preserving score.py's
    canonical-name expectation. See Decision Gate log #6 (2026-04-19).
    """
    t0 = time.perf_counter()
    # MCP-tool schema -> Anthropic tool schema, with colon bijection
    transport_to_canonical: dict[str, str] = {}
    anth_tools = []
    for t in tools:
        transport_name = t["name"].replace(":", "__")
        transport_to_canonical[transport_name] = t["name"]
        anth_tools.append(
            {"name": transport_name, "description": t["description"], "input_schema": t["inputSchema"]}
        )
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=anth_tools,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    tool_call: dict[str, Any] | None = None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            canonical_name = transport_to_canonical.get(block.name, block.name)
            tool_call = {"tool_name": canonical_name, "input": block.input}
            break

    usage = getattr(resp, "usage", None)
    return {
        "tool_call": tool_call,
        "latency_ms": latency_ms,
        "tokens_in": getattr(usage, "input_tokens", 0) if usage else 0,
        "tokens_out": getattr(usage, "output_tokens", 0) if usage else 0,
        "stop_reason": getattr(resp, "stop_reason", None),
    }


def _stub_result(prompt: dict[str, Any], condition: str, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    gt = prompt["ground_truth"]
    if gt.get("op_id") is None:
        # no-valid-tool: 80% refusal in stub (correct)
        called = rng.random() > 0.8
        if not called:
            return {"tool_call": None, "latency_ms": 50.0, "tokens_in": 100, "tokens_out": 20, "stop_reason": "end_turn"}
    tool_name = (
        f"{prompt['tenant']}-{prompt['api']}-{gt['op_id']}"
        if condition == "per-op"
        else f"{prompt['tenant']}:{prompt['api']}"
    )
    return {
        "tool_call": {"tool_name": tool_name, "input": {"action": gt.get("op_id")}},
        "latency_ms": 100.0 + rng.random() * 50,
        "tokens_in": 200,
        "tokens_out": 40,
        "stop_reason": "tool_use",
    }


def run(
    prompts: list[dict[str, Any]],
    specs_dir: Path,
    models: list[str],
    conditions: list[str],
    runs: int,
    scalability: list[int] | None,
    dry_run: bool,
    parallel: int,
) -> list[dict[str, Any]]:
    client = None
    if not dry_run:
        import anthropic  # type: ignore[import-not-found]
        client = anthropic.Anthropic()

    spec_cache: dict[str, dict[str, Any]] = {}

    def _spec(api: str) -> dict[str, Any]:
        if api not in spec_cache:
            spec_cache[api] = _spec_for(api, specs_dir)
        return spec_cache[api]

    jobs: list[tuple[dict[str, Any], str, str, int, int | None]] = []
    for p in prompts:
        for m in models:
            for c in conditions:
                for r in range(runs):
                    jobs.append((p, m, c, r, None))
    if scalability:
        per_op_prompts = prompts
        for scale in scalability:
            for p in per_op_prompts:
                for m in models:
                    for r in range(runs):
                        jobs.append((p, m, "per-op", r, scale))

    def _one(job: tuple[dict[str, Any], str, str, int, int | None]) -> dict[str, Any]:
        p, m, c, r_idx, scale = job
        tools = _tools_for_condition(c, p["api"], p["tenant"], _spec(p["api"]), scale=scale)
        if dry_run:
            seed = hash((p["id"], m, c, r_idx, scale)) & 0xFFFF
            result = _stub_result(p, c, seed)
        else:
            try:
                result = _call_anthropic(client, m, tools, p["prompt"])
            except Exception as e:
                result = {"tool_call": None, "latency_ms": 0, "tokens_in": 0, "tokens_out": 0, "stop_reason": f"error: {e}"}
        return {
            "prompt_id": p["id"],
            "model": m,
            "condition": c,
            "run_idx": r_idx,
            "scale": scale,
            "n_tools": len(tools),
            **result,
        }

    results: list[dict[str, Any]] = []
    if parallel <= 1 or dry_run:
        for j in jobs:
            results.append(_one(j))
    else:
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            for rec in ex.map(_one, jobs):
                results.append(rec)
    return results


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", required=True, type=Path)
    ap.add_argument("--specs-dir", required=True, type=Path)
    ap.add_argument("--models", nargs="+", default=["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"])
    ap.add_argument("--conditions", nargs="+", default=["coarse", "per-op", "enriched-single"])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--scalability", nargs="*", type=int, default=[], help="e.g. 50 100 200 (per-op only)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing (or use --dry-run)", file=sys.stderr)
        return 2

    prompts = _load_jsonl(args.prompts)
    if args.limit:
        prompts = prompts[: args.limit]
    records = run(
        prompts=prompts,
        specs_dir=args.specs_dir,
        models=args.models,
        conditions=args.conditions,
        runs=args.runs,
        scalability=args.scalability or None,
        dry_run=args.dry_run,
        parallel=args.parallel,
    )
    out_lines = [json.dumps(r, sort_keys=True) for r in records]
    if args.out:
        args.out.write_text("\n".join(out_lines) + "\n")
    else:
        print("\n".join(out_lines))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
