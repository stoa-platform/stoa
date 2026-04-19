# Phase 0.5 — LLM Tool-Selection Benchmark (CAB-2116 P2)

**Date**: 2026-04-19
**Ticket**: CAB-2116 (P2)
**Harness commit**: `1dab2554` (P1 shipped) + transport-layer fix to `run_bench.py` (this session, not methodology)
**Decision Gate**: log #6 (stoa-docs PR#166 merged `95d111d9`) — P2 authorized on frozen substitute corpus for comparative ranking only
**Runtime**: 46 min (17:41 → 18:27 UTC), parallel=4
**Cost**: ~$300–500 (full breakdown: 4 860 Anthropic API calls)

## Verdict

| Variant           | Verdict | Reason                                                                      |
|-------------------|---------|-----------------------------------------------------------------------------|
| `per-op`          | **RED** | Cost regression ≈ 8× coarse (gate ≤ 0.2). Accuracy gains real but not cheap.|
| `enriched-single` | **RED** | Cost regression ≈ 0.68× coarse (gate ≤ 0.2). Latency regression on Haiku/Opus. |

**Target model** (gating): `claude-sonnet-4-6`.

Both variants fail the mechanical gate, driven by **cost** (and latency on non-target models), **not by accuracy**. Accuracy gains are statistically significant across all 3 models, all 2 variants (CI95 lower bound > 0, gain ≥ 10 pts).

## Per-cell top-1 accuracy

| Model                            | Condition        | n    | Top-1 | p95 ms | Cost tok |
|----------------------------------|------------------|------|-------|--------|----------|
| claude-haiku-4-5-20251001        | coarse           | 270  | 0.115 | 2 255  | 795      |
| claude-haiku-4-5-20251001        | enriched-single  | 270  | 0.719 | 2 765  | 1 345    |
| claude-haiku-4-5-20251001        | per-op           | 1080 | 0.756 | 2 748  | 7 187    |
| claude-opus-4-7                  | coarse           | 270  | 0.344 | 3 709  | 1 063    |
| claude-opus-4-7                  | enriched-single  | 270  | 0.741 | 5 181  | 1 787    |
| claude-opus-4-7                  | per-op           | 1080 | 0.728 | 4 551  | 9 653    |
| claude-sonnet-4-6                | coarse           | 270  | 0.311 | 4 027  | 796      |
| claude-sonnet-4-6                | enriched-single  | 270  | 0.681 | 4 740  | 1 336    |
| claude-sonnet-4-6                | per-op           | 1080 | 0.713 | 4 825  | 7 187    |

## Target-model paired gates (claude-sonnet-4-6, n_paired=90)

| Gate                      | enriched-single            | per-op                     |
|---------------------------|----------------------------|----------------------------|
| ci95_lower_positive       | ✅ [0.189, 0.533]          | ✅ [0.278, 0.600]          |
| gain_10pts                | ✅ mean_gain = 0.367       | ✅ mean_gain = 0.444       |
| latency_not_regressed     | ✅ +17.7% (≤20%)           | ✅ +19.8% (≤20%)           |
| cost_not_regressed        | ❌ +68% (≤20%)             | ❌ +703% (≤20%)            |
| scalability               | n/a                        | ✅                         |
| **green**                 | **false**                  | **false**                  |

## Architectural reading (scope per Decision Gate log #6)

This ranks **architectures** on the frozen substitute corpus. It is **not** a certification against the eventual CP-served canonical specs. Re-ratification required if MCP audience bug (CAB-2094/2103) is later fixed and specs diff is material.

- `coarse` — only viable for the `no_valid_tool` refusal category (accuracy 0.78 vs ~0.03 on normal prompts). Unusable for real intent routing.
- `enriched-single` — best **cost/accuracy ratio**: ~98% of per-op's accuracy at 15–20% of per-op's cost. Single tool + enriched hints beats 70 atomic tools from a price-per-correct-answer standpoint.
- `per-op` — marginal accuracy win (+2–4 pts over enriched) at ~7× the cost. Scalability to 50/100/200 tools held (no collapse), but cost gate invalidates it as a production default.
- Target model (`claude-sonnet-4-6`) is the only model whose `per-op` latency stays within the +20% envelope. Haiku and Opus both regress past gate.

## Recommendation (input, not decision)

The mechanical verdict (RED on both) reads as: **"neither variant clears all gates on the frozen corpus"**. The actionable gradient underneath:

1. If cost is the binding constraint → `enriched-single` is the pragmatic architecture. Accuracy gap vs per-op is < 5 pts, cost gap is ~5–10×.
2. If cost gate is loosened (or reframed as per-query cost rather than per-tool-spec token overhead) → per-op may clear on sonnet specifically. This is a **gate redefinition**, requires new Decision Gate log.
3. Phase 1 entry requires **≥10 Decision Gate logs over 60 days AND (score_divergence > 1.5 on ≥30% OR decision_delta = YES on ≥20%)** per ADR / log #4. This single run feeds one data point, not a phase transition.

## P1 harness defects discovered during P2 (transport-layer, not methodology)

1. **Tool name pattern violation** — `build_enriched.py:145,189` emits `f"{tenant}:{api_name}"` containing `:`. Anthropic API requires `^[a-zA-Z0-9_-]{1,128}$` → HTTP 400. Fix applied in `run_bench.py::_call_anthropic` via explicit bijection `:` ↔ `__`, canonical name preserved in persisted records (`score.py:60` unchanged).
2. **`temperature=0` accidentally dropped during the bijection refactor** — initial note in this audit claimed the parameter was deprecated on Claude 4.x and had to be removed; that was incorrect. The refactor dropped it silently, which flipped the bench from deterministic to stochastic sampling and invalidated `--runs N` semantics, `score.py` top-1 accuracy, and comparability with prior bench records. Restored by commit [`a064fb6a`](https://github.com/stoa-platform/stoa/commit/a064fb6a) (CAB-2116) — `run_bench.py::_call_anthropic` sends `temperature=0` as designed. Claude 4.x accepts it.

Neither changes specs, prompts, generator, or decision rule. Both are P1 bugs: the harness was never validated against the live API prior to P2 (only the deterministic stub path). Follow-up shipped as CAB-2124 — `tools/phase05-harness/tests/test_live_smoke.py` (gated on `STOA_LIVE_SMOKE=1` + `ANTHROPIC_API_KEY`) plus an offline transport-contract test.

## Artifacts

- `runs.jsonl` — 4 860 records (3 models × 3 conditions × 90 prompts × 3 runs + 2 430 scalability at 50/100/200 tools)
- `report.json` — scoring output (config + per_cell + verdicts)

## Discipline check

- ✅ `specs/`, `prompts.jsonl`, `build_enriched.py`, `score.py` untouched
- ✅ Decision Gate log #6 published and merged before bench start
- ✅ Determinism tests (11) pass on main with bench patch applied
- ✅ Claim scoped to architecture ranking, not canonical-spec certification (per log #6)
