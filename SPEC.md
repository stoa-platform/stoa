# Spec: CAB-2214 — CAB-2213 Phase 6.0 Guardrails Red Contract

> Phase 6.0 branch: docs, cardinality evidence, and red-test scaffolding only.
> Master ticket: CAB-2213.
> Phase ticket: CAB-2214.
> Validated plan: `docs/plans/2026-05-11-guardrails-non-mcp-4b-full.md`.
> Decision log: `docs/decisions/2026-05-11-guardrails-non-mcp-4b-full.md`.
> Council S2: 8.0/10 Go after E6 `stale_reason` bounded enum lock.

## Problem

The current Security & Guardrails observability surface can show runtime guardrail
trips, but it cannot prove whether zero trips means "traffic was evaluated and
allowed" or "no guardrail evaluation happened." Existing gateway counters are
trip-oriented and legacy-shaped, and the Control Plane API/UI infer too much from
missing samples.

## Goal

Introduce an additive, low-cardinality guardrails metrics contract that covers MCP
and selected non-MCP gateway paths, then expose a server-derived five-state
semantic contract to `/observability/security`.

Phase 6.0 prepares the contract and red tests. It must not implement gateway
producers, API readers, UI rendering, rollout jobs, or production smoke.

## API And Metrics Contract

Gateway metrics:

```text
stoa_guardrails_evaluations_total{deployment_mode,surface,guardrail}
stoa_guardrails_decisions_total{deployment_mode,surface,guardrail,decision}
```

Locked enums:

- `deployment_mode`: `edge-mcp | sidecar | proxy | shadow | unknown`
- `surface`: `mcp | api_proxy | dynamic_proxy | ws_proxy`
- `guardrail`: `pii | injection | prompt_guard | content_filter | rate_limit`
- `decision`: `allow | redact | block | error`

Forbidden decision values: `not_applicable`, `bypass`, `flag`, `rate_limited`.

Control Plane API guardrails block:

```ts
{
  state:
    | 'metrics_unavailable'
    | 'no_evaluations'
    | 'evaluations_zero_trips'
    | 'trips_observed'
    | 'stale_data';
  evaluations_count: number | null;
  decisions_count: number | null;
  trips_count: number | null;
  error_count: number | null;
  last_evaluation_delta_at: string | null;
  last_decision_delta_at: string | null;
  scrape_sample_at: string | null;
  source_healthy: boolean;
  stale_reason:
    | 'prom_unreachable'
    | 'scrape_gap'
    | 'producer_absent'
    | 'stale_unknown'
    | null;
  by_guardrail: Record<string, GuardrailSemanticState>;
}
```

The API owns `state`. The UI renders it and must not recompute it from counts or
timestamps.

## Acceptance Criteria

| ID | Criterion | Red-test owner |
| --- | --- | --- |
| AC1 | New `evaluations_total` and `decisions_total` counters exist with only bounded labels and `decision in allow|redact|block|error`. | Gateway |
| AC2 | MCP tool-call path increments one evaluation per executed guardrail policy and emits all four decision values. | Gateway |
| AC3 | Non-MCP `api_proxy` and `dynamic_proxy` emit observe-only metrics without request/response behavior changes. | Gateway |
| AC4 | cp-api ships server-derived `state`, four timestamp/health fields, and capped freshness semantics. | API |
| AC5 | UI renders five backend states verbatim, preserves `null`, and keeps AR-1 wording. | UI |
| AC6 | PR-3A fields and legacy metric readers remain compatible during the new-counter window. | API |
| AC7 | Cardinality stays within the <=500 series budget and forbidden labels are absent. | Gateway |
| AC8 | Phase 6.6 smoke fixtures are synthetic only: no real PII and no real customer prompt content. | Docs/API test harness |
| AC9 | Legacy removal is impossible inside Phase 6 and requires a separate plan after the A7 closure checklist. | Docs/API test harness |
| AC10 | Producer presence distinguishes `no_evaluations` from `metrics_unavailable` via zero-initialized bounded series or an approved gauge. | Gateway |
| AC11 | Skipped bodies never increment evaluations or decisions. | Gateway |
| AC12 | cp-api state precedence is locked, and UI never overrides backend `state`. | UI/API |
| AC13 | `trips_count = redact + block`; `error_count = error`; error never contributes to trips. | API |
| AC14 | Per-guardrail health is independent; one stale guardrail does not make healthy guardrails stale. | API |
| AC15 | Production smoke validates only safe states; fault-injection states are dev/k3d or staging only. | Docs/API test harness |
| AC16 | Council gate is archived before implementation code lands. | Docs/API test harness |
| AC17 | `stale_reason` is a bounded enum and never leaks raw Prometheus internals. | API |

## Edge Cases

| ID | Case | Expected |
| --- | --- | --- |
| E1 | Prometheus query failure | `state="metrics_unavailable"`, null counts, `source_healthy=false`, bounded `stale_reason`. |
| E2 | Fresh scrape, zero traffic | `state="no_evaluations"` when producer presence exists. |
| E3 | Evaluations happened, no trips | `state="evaluations_zero_trips"` and `trips_count=0`. |
| E4 | Redact + block + error in window | `trips_count=redact+block`, `error_count=error`. |
| E5 | Non-JSON, oversized, streaming, or structurally not-applicable body | No evaluation and no decision increment. |
| E6 | One guardrail stale, others healthy | Per-guardrail stale only; top-level stays healthy unless all guardrails are stale. |
| E7 | Production smoke request would require fault injection | Forbidden unless a separate SRE-approved chaos plan exists. |

## Out Of Scope For Phase 6.0

- Gateway producer implementation.
- cp-api Prometheus reader implementation.
- UI rendering implementation.
- Production, staging, or k3d smoke execution.
- Legacy metric removal.
- Security Posture / Security & Guardrails IA changes.
- Synthetic production fallback data.
