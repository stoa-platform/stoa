# Phase 0.5 — LLM tool-selection benchmark harness

> **STATUS: P1 contract — FROZEN on 2026-04-19.**
> Any change to: specs in `specs/`, `build_enriched.py`, `prompts.jsonl`, the decision rule below, or the target model **requires** a new Decision Gate log entry before P2 runs.
> Pins are enforced mechanically by `tests/test_determinism.py` (`test_spec_sha256_pinned`, `test_generator_sha_matches_pin`).

Gate before Phase 1 (catalog CRDs): evaluate whether `per-op` or `enriched-single` beats `coarse` on LLM tool-selection accuracy, on a non-demo workload, with a pre-registered binary decision rule — so Phase 1 cannot be p-hacked ex post.

Ticket: [CAB-2116](https://linear.app/hlfh-workspace/issue/CAB-2116) — parent: CAB-2113.

---

## Pinned artefacts

| File | sha256 |
|------|--------|
| `specs/banking-services-v1-2.yaml` | `79689dfbee7347e2fb00d2f8979058c97a65955560d7552e2ea95e698a4d8249` |
| `specs/payment-api.yaml` | `144c2daa521e00c413c3ce3d95084a728ba03368391b4d6e4a7053100ca9fe17` |
| `specs/fapi-accounts.yaml` | `b9822eeed1d24fa1896d636baa062b7a2a29bcec00165b3830049d6222fad5c5` |
| `build_enriched.py` (generator) | `06aa6308d20c82bb2fce080bf4bf524e664c341c91fbd7e1c18163bfb5818305` |
| `prompts.jsonl` | pinned by `test_prompt_corpus_counts` + `test_ground_truth_resolves_to_operation_ids` |

The generator sha is also persisted to `.generator.sha256` and checked by `test_generator_sha_matches_pin`.

### Spec origin note (pre-P2 swap required)

These snapshots are **substitutes** for the ticket's named APIs. At the time of freeze the `stoa-platform-cloud` MCP OAuth audience claim was empty (see `gotchas/gateway_mcp_audience`); we could not fetch the canonical CP-API-served specs. Origins:

| Snapshot name (ticket) | Actual source | Rationale |
|------------------------|---------------|-----------|
| `banking-services-v1-2.yaml` | OBIE UK Open Banking Read/Write v3.1, AIS + PIS merged | Need ≥50 ops, banking domain, public & stable |
| `payment-api.yaml` | `tenants/middle-earth-bank/apis/payment-api/openapi.yaml` (repo) | STOA's own demo spec — identical to what live tenants expose |
| `fapi-accounts.yaml` | OBIE UK Open Banking Confirmation of Funds v3.1 | FAPI-shaped, banking domain |

**Pre-P2 action:** when MCP audience is fixed, re-fetch the 3 canonical CP-API specs into `specs.candidate/`, diff vs pinned snapshots, open a Decision Gate log to ratify (or reject) the swap. If ratified, update sha256 pins and re-freeze.

---

## Decision contract (frozen)

### The three conditions

| # | Name | How tools are presented to the LLM |
|---|------|-----------------------------------|
| A | `coarse` | 1 tool per API, `inputSchema = {action, params}` opaque |
| B | `per-op` | N tools per API, 1 per OpenAPI operation, full per-op input schema |
| C | `enriched-single` | 1 tool per API, `inputSchema` has `action` enum + `params` oneOf over per-op `$defs` with `action: const` discriminator |

Condition C is generated **deterministically** by `build_enriched.py` — no LLM in the loop. See `build_enriched.build_enriched()`.

### Primary metric

**Top-1 tool-selection accuracy.** Binary per prompt: did the model emit, on the first `tools/call`, the expected `(tool_name, op_id)` pair with no retry and no clarification? Nothing else is scored.

### Corpus

- 90 prompts total across 3 APIs (30 per API).
- ≥20% distractors (intent ambiguous between adjacent ops).
- ≥10% no-valid-tool (expected: no `tools/call`; any call = false positive).
- Ground-truth rubric embedded in `prompts.jsonl` per line (`ground_truth.op_id`).
- Scoring = deterministic (`score.py`). No LLM-as-judge.

### Target model and aggregation rule

- **Target model (produced verdict is about this one):** `claude-sonnet-4-6`.
- Also run: `claude-opus-4-7`, `claude-haiku-4-5-20251001`, same corpus, same runs.
- **Aggregation rule (anti cherry-pick):** a variant's verdict is GREEN **only if** it is GREEN on Sonnet **and** on at least one other model. Any other combination → RED.

### Per-variant verdict (evaluated independently for `per-op` and `enriched-single`)

A variant X (compared to `coarse`) is **GREEN** iff, on the target model AND ≥1 other model, **all** of:

1. `mean_gain(X - coarse) ≥ +0.10` absolute top-1 accuracy.
2. Bootstrap 95% CI of paired per-prompt score-diff (`variant_score - coarse_score`) has lower bound **strictly > 0**.
3. No ≥+20% regression on median token cost per prompt.
4. No ≥+20% regression on p95 latency of first `tools/call`.
5. *(per-op only)* scalability: `accuracy@200_ops ≥ 0.9 × accuracy@50_ops`.

Any single check failing on either required model ⇒ **RED** for that variant.

### Scenario → action table

| per-op | enriched-single | Action |
|--------|-----------------|--------|
| GREEN | RED | Phase 1 CRDs (per-op schema) opens |
| RED | GREEN | Phase 1 per-op CRDs **cancelled**; open separate ticket to promote `enriched-single` |
| GREEN | GREEN | Phase 1 per-op CRDs opens; `enriched-single` noted as fallback |
| RED | RED | `coarse` overlay runtime sanctified as terminal state; Phase 1 cancelled |

### Bootstrap config (pinned)

- Iterations: `10_000`
- Seed: `20_260_419` (ISO date of freeze)
- Defined in `score.py`, asserted by `test_score_end_to_end_stub_pipeline`.

---

## Layout

```
tools/phase05-harness/
├── README.md              # this file — the frozen contract
├── build_enriched.py      # deterministic generator (coarse/per-op/enriched-single)
├── run_bench.py           # 3 conditions × N prompts × M models × R runs driver
├── score.py               # deterministic scorer + verdict engine
├── prompts.jsonl          # 90 prompts + ground-truth rubric
├── .generator.sha256      # pinned hash of build_enriched.py
├── specs/                 # pinned OpenAPI snapshots
└── tests/
    └── test_determinism.py
```

---

## Usage

### Sanity check (no API calls)

```bash
cd tools/phase05-harness
python3 -m pytest tests/ -q
python3 run_bench.py --prompts prompts.jsonl --specs-dir specs --dry-run --runs 1 --out /tmp/runs.jsonl
python3 score.py --prompts prompts.jsonl --runs /tmp/runs.jsonl --out /tmp/report.json
```

### Full P2 run (requires `ANTHROPIC_API_KEY`)

```bash
python3 run_bench.py \
    --prompts prompts.jsonl \
    --specs-dir specs \
    --models claude-opus-4-7 claude-sonnet-4-6 claude-haiku-4-5-20251001 \
    --conditions coarse per-op enriched-single \
    --runs 3 \
    --scalability 50 100 200 \
    --parallel 4 \
    --out runs.jsonl

python3 score.py --prompts prompts.jsonl --runs runs.jsonl --out report.json
```

Artefacts (raw `runs.jsonl` + `report.json` + any prompts diff) land in `docs/audits/2026-XX-XX-phase05-harness/`. Per-variant verdict is computed **mechanically** by `score.py` — humans read, do not override.

---

## What this benchmark is NOT

- Not "end-to-end task success" — only tool selection is scored.
- Not "quality of response" — model output is ignored apart from `tools/call`.
- Not "LLM-as-judge" — rubric is static and deterministic.
- Not "general AI eval" — scope is the per-op-vs-coarse question for STOA's catalog investment decision.

## P2 gate

`tests/test_determinism.py` must pass on `main` before any P2 run is launched. Any drift caught by the sha256 pins ⇒ **stop** and patch via a new Decision Gate log.
