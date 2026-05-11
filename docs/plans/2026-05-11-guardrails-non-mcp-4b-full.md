---
id: plan-2026-05-11-guardrails-non-mcp-4b-full
triggers: [a, b]
validation_status: draft
challenge_ref: ""
source_plan_ref: docs/plans/2026-05-09-observability-data-visibility.md
source_decision_ref: docs/decisions/2026-05-09-observability-data-visibility.md
launch_signal: "Operator requested go phase 6 on 2026-05-11; maps to Q8.6 explicit signal to open the separate MEGA."
---

# Plan - Phase 6 Guardrails Non-MCP + 4B-Full

## Decision Gate

This plan matches HLFH Decision Challenge triggers:

- `a`: estimated work is greater than 5h.
- `b`: it changes product-facing observability semantics for `/observability/security` and Prometheus public metric contracts.

No implementation may start while `validation_status != validated`.

Required before code:

1. External non-Claude challenger verdict in `docs/decisions/2026-05-11-guardrails-non-mcp-4b-full.md`.
2. Council review if impact score is HIGH or above.
3. Phase ownership claim per phase (see Phase Ownership matrix below).

## Phase Ownership

Per CLAUDE.md multi-instance protocol (`.claude/claims/<ID>.json` + atomic `mkdir` lock). End-to-end ownership: whoever claims a phase finishes it. Stale claim auto-releases after 2h of inactivity.

| Phase | Component owner | Claim path |
|---|---|---|
| 6.0 | platform | `.claude/claims/phase-6-0-validation.json` |
| 6.1 | gateway | `.claude/claims/phase-6-1-gateway-metrics.json` |
| 6.2 | gateway | `.claude/claims/phase-6-2-mcp-coverage.json` |
| 6.3 | gateway | `.claude/claims/phase-6-3-nonmcp-observe.json` |
| 6.4 | cp-api | `.claude/claims/phase-6-4-api-reader.json` |
| 6.5 | cp-ui | `.claude/claims/phase-6-5-ui-states.json` |
| 6.6 | sre | `.claude/claims/phase-6-6-runtime-smoke.json` |

A single actor may chain claims across phases owned by the same component (e.g., one gateway implementer covering 6.1 → 6.2 → 6.3) provided each claim file is created and released in order.

## Objective

Make `/observability/security` distinguish "no guardrail evaluations happened" from "evaluations happened and produced zero trips" by introducing bounded guardrail evaluation and decision counters across MCP and non-MCP gateway paths.

## Launch Signal

Phase 6 was deferred by the validated Observability Data Visibility plan. It may start only if at least one Q8.6 signal exists.

Current signal:

- Operator explicitly requested `go phase 6` on 2026-05-11.

The challenger must verify whether this is sufficient product confirmation for Q8.6 signal 1, 2, 3, or 4. If not, this plan remains `draft` or becomes `challenged`.

## Context

Already delivered:

- Phase 3 wording made the current empty state honest but minimal: "No guardrail trip samples in window".
- PR-3A guardrails runtime truth contract is validated in `docs/plans/2026-05-10-guardrails-runtime-truth-contract.md`.
- `/observability/security` already preserves `null` vs `0`, stale vs unavailable, and disabled vs enabled states.
- Existing gateway guardrail counters only count selected trip outcomes. They do not count total evaluations, so the product cannot prove "evaluated and allowed".

Canonical cross-references (challenger must treat as binding context):

- **AR-1 canonical** — `docs/plans/2026-05-07-observability-data-integrity.md` line 63: "Clarifier — Posture = état/findings/score statique ; Guardrails = events runtime. Pas de fusion (personas distincts: compliance officer vs SRE)." Status: `validated 2026-05-07`. Phase 6 preserves AR-1 — no merge of Security Posture with Security & Guardrails; distinct subtitles remain.
- **PR-3A wording elaboration** — `docs/plans/2026-05-10-guardrails-runtime-truth-contract.md`. Phase 6 must not change AR-1 wording (see Anti-Goals).

Current relevant metric readers:

- `control-plane-api/src/services/gateway_metrics_service.py` reads:
  - `stoa_guardrails_pii_detected_total`
  - `stoa_guardrails_injection_blocked_total`
  - `stoa_guardrails_content_filtered_total`
  - `stoa_prompt_guard_detected_total`
  - rate-limit counters

Current primary producer:

- `stoa-gateway/src/mcp/handlers.rs` runs guardrail checks around MCP tool calls and records legacy counters on redaction/block/sensitive outcomes.

Phase 6 extends this without treating Phase 2 fixtures or UI wording as runtime proof.

## Scope

In:

- New low-cardinality gateway counters for guardrail evaluations and decisions.
- MCP producer coverage for pass, redacted, flagged, blocked, and rate-limited outcomes where applicable.
- Non-MCP producer coverage for guardrail-applicable proxy paths, initially in observe-only mode unless the challenger validates enforcement changes.
- Control Plane API reader support for old and new metrics during a compatibility window.
- `/observability/security` semantic split into five states:
  - `metrics_unavailable`
  - `no_evaluations`
  - `evaluations_zero_trips`
  - `trips_observed`
  - `stale_data`
- Tests proving `null`, `0`, no-evaluation, zero-trip, trip, stale, and unavailable states remain distinct.
- Documentation of metric names, label policy, and rollback.

Out:

- No migration of `audit_events`.
- No payload storage or raw payload telemetry.
- No tenant, route, policy, tool, trace, span, request, consumer, raw path, URL, or payload-derived label on the new counters unless a challenger explicitly accepts the cardinality risk and the plan is amended.
- No OPA runtime event ingestion unless separately specified.
- No Security Posture merge with Security & Guardrails.
- No broad guardrail enforcement behavior change for non-MCP traffic in the first PR unless explicitly validated.

## Proposed Metric Contract

New counters:

```text
stoa_guardrails_evaluations_total{deployment_mode, surface, guardrail}
stoa_guardrails_decisions_total{deployment_mode, surface, guardrail, decision}
```

Allowed label values:

| Label | Values | Notes |
|---|---|---|
| `deployment_mode` | `edge-mcp`, `sidecar`, `proxy`, `shadow`, `unknown` | Bounded ADR-024 mode projection. |
| `surface` | `mcp`, `api_proxy`, `dynamic_proxy`, `ws_proxy` | Bounded producer call-site. |
| `guardrail` | `pii`, `injection`, `prompt_guard`, `content_filter`, `rate_limit` | Bounded feature enum. |
| `decision` | `allow`, `redact`, `flag`, `block`, `rate_limited` | Bounded outcome enum. |

Cardinality budget:

```text
evaluations_total <= 5 modes * 4 surfaces * 5 guardrails = 100 series
decisions_total <= 5 modes * 4 surfaces * 5 guardrails * 5 decisions = 500 series
```

The prior sketch in `docs/plans/2026-05-09-observability-data-visibility.md` mentioned `{mode, tenant, route, policy}`. This plan intentionally starts narrower because `tenant_id`, route, and policy labels are limited or owner-approved under `docs/observability/telemetry-contract.md` and `docs/observability/gateway-metrics-cardinality.md`.

If tenant-scoped drilldown is required, it should come from server-side filtered traces/logs or an explicitly challenged follow-up contract, not from this first Prometheus counter set.

## API Contract

Extend `GET /v1/admin/gateways/metrics?range=<range>` guardrails block with additive fields:

```ts
{
  guardrails: {
    evaluations_total: number | null,
    decisions_total: number | null,
    trips_total: number | null,
    no_evaluations: boolean | null,
    evaluation_sample_at: string | null,
    decision_sample_at: string | null,
    semantic_state:
      | "metrics_unavailable"
      | "no_evaluations"
      | "evaluations_zero_trips"
      | "trips_observed"
      | "stale_data",
    by_guardrail: Record<
      "pii" | "injection" | "prompt_guard" | "content_filter" | "rate_limit",
      {
        evaluations: number | null,
        trips: number | null,
        state:
          | "metrics_unavailable"
          | "no_evaluations"
          | "evaluations_zero_trips"
          | "trips_observed"
          | "stale_data"
      }
    >
  }
}
```

Compatibility rules:

- Existing PR-3A fields remain unchanged.
- Existing legacy counters remain readable during the compatibility window.
- `null` remains unknown/unavailable/no sample, never fake zero.
- `0` means the backend can prove the count over the selected range.
- `semantic_state` is derived server-side so tenant authorization and metric interpretation remain backend-owned.

### Sample Timestamp and `stale_data` Semantics

`evaluation_sample_at` and `decision_sample_at` are defined as:

- The RFC3339 UTC timestamp of the most recent Prometheus scrape for which the counter value strictly increased within the selected range. Operational definition: `max(timestamp WHERE delta(stoa_guardrails_evaluations_total[scrape_interval]) > 0)` over the range.
- If no scrape recorded a positive delta in the range, the field is `null` and `no_evaluations` (or `metrics_unavailable` if the counter series is absent entirely) applies.

`stale_data` threshold (server-derived, **subject to challenger lock**):

- For ranges ≤ 1h: `stale_data` triggers when `now - max(evaluation_sample_at, decision_sample_at) > max(2 × scrape_interval, 5 min)`. Default scrape interval = 30s → effective threshold = 5 min.
- For ranges > 1h: `stale_data` triggers when `now - max(evaluation_sample_at, decision_sample_at) > range / 12`, with a floor of 5 min. Rationale: longer windows tolerate longer scrape gaps proportionally.

UI must not re-derive `stale_data` from raw timestamps — the API ships the precomputed `semantic_state` and the UI renders it as-is. This preserves AR-1 boundary (backend owns runtime truth).

## Compatibility Window

Legacy guardrail counters remain readable during the compatibility window:

- `stoa_guardrails_pii_detected_total`
- `stoa_guardrails_injection_blocked_total`
- `stoa_guardrails_content_filtered_total`
- `stoa_prompt_guard_detected_total`
- rate-limit counters

Window closes when **both** conditions hold:

1. Phase 6.6 smoke validates the 5 semantic states (`metrics_unavailable`, `no_evaluations`, `evaluations_zero_trips`, `trips_observed`, `stale_data`) in production, archived under `docs/audits/<YYYY-MM-DD>-phase-6-rollout/findings.md`.
2. At least 14 days of observation pass with no consumer (dashboard, alert rule, third-party export, internal script) querying the legacy counter names. Verification: Prometheus query-stats audit (`prometheus_engine_queries_total`) shows zero non-canary reads of legacy counter names over the 14-day window.

Legacy counter removal is scheduled by a **separate plan** opened after window closure. Phase 6 does not remove legacy counters under any condition (binding anti-goal). The 14-day floor is challenger-revisable upward if downstream dashboards or partner integrations are identified.

## Phases

### Phase Dependency Graph

```
6.0 (validation) ─→ 6.1 (gateway metrics) ─┬─→ 6.2 (MCP coverage) ──┐
                                            └─→ 6.3 (non-MCP obs)  ─┤
                                                                    ├─→ 6.4 (API reader) ─→ 6.5 (UI states) ─→ 6.6 (smoke)
```

Rules:

- **6.0 → 6.1**: validation must finish before producer code lands.
- **6.1 → {6.2, 6.3}**: 6.1 ships the counter contract on the producer side; 6.2 and 6.3 are independent call-site instrumentations and may run in parallel after 6.1.
- **{6.2, 6.3} → 6.4**: 6.4 starts only when 6.2 has shipped (cp-api unit tests rely on MCP allow/redact/flag/block samples). 6.3 may still be in flight; the cp-api reader is agnostic to which call-sites produce.
- **6.4 → 6.5**: strict — UI consumes new API fields; no UI work before backend ships and tests pass.
- **6.5 → 6.6**: smoke validates the full stack, runs last.

A phase may not be marked complete until all its predecessors are complete and its DoD is binary-checked.

### Phase 6.0 - Validation and Red Tests

Goal: lock the contract before implementation.

Deliverables:

- This plan transitions from `draft` to `validated`.
- A small SPEC addendum may be created if the branch root `SPEC.md` is replaced by a ticket-specific spec in the implementation branch; current root `SPEC.md` belongs to an older CAB and must not be reused silently.
- Failing tests are added for the accepted acceptance criteria before production code changes.

DoD:

- [ ] External challenger validates or challenges the metric label set.
- [ ] Council score meets the required threshold if impact score is HIGH or above.
- [ ] Red tests exist in gateway, API, and UI slices before corresponding implementation.

### Phase 6.1 - Gateway Metric Contract

Goal: add producer-side counters with bounded labels.

Owned paths:

- `stoa-gateway/src/metrics.rs`
- `stoa-gateway/src/guardrails/`
- targeted gateway tests
- `docs/observability/gateway-metrics-cardinality.md`

DoD:

- [ ] `stoa_guardrails_evaluations_total` and `stoa_guardrails_decisions_total` are exported by `/metrics`.
- [ ] Unit tests prove the new metrics do not include forbidden labels.
- [ ] Legacy counters continue to emit for compatibility.
- [ ] `cargo fmt --check` and `cargo test` pass locally.

### Phase 6.2 - MCP Coverage

Goal: instrument MCP tool-call guardrail pass and trip paths.

Owned paths:

- `stoa-gateway/src/mcp/handlers.rs`
- `stoa-gateway/src/guardrails/`
- targeted gateway tests

DoD:

- [ ] A clean MCP request increments evaluation and `allow` decision counters.
- [ ] PII redact increments evaluation and `redact`.
- [ ] Content sensitive/flag increments evaluation and `flag`.
- [ ] Injection/content block increments evaluation and `block`.
- [ ] Existing trip counters still increment as before.

### Phase 6.3 - Non-MCP Observe-Only Coverage

Goal: evaluate guardrails on non-MCP traffic without mutating or blocking traffic in the first implementation slice.

Candidate paths to confirm during implementation:

- `stoa-gateway/src/proxy/api_proxy_handler.rs`
- `stoa-gateway/src/proxy/dynamic.rs`
- `stoa-gateway/src/ws/proxy.rs` only if payload semantics are safe and bounded

DoD:

- [ ] At least one HTTP non-MCP proxy path emits evaluations and decisions in observe-only mode.
- [ ] Body handling does not consume streaming bodies unsafely.
- [ ] No request/response behavior changes for non-MCP traffic unless a validated amendment allows it.
- [ ] Tests prove non-JSON or oversized bodies are skipped or counted as `allow` without payload logging.

### Phase 6.4 - Control Plane API Reader

Goal: expose the semantic split without breaking PR-3A fields.

Owned paths:

- `control-plane-api/src/services/gateway_metrics_service.py`
- `control-plane-api/tests/test_gateway_observability_router.py`
- schemas only if the router already uses explicit response models

DoD:

- [ ] API reads new evaluation and decision counters.
- [ ] API supports old trip counters during compatibility.
- [ ] API returns `no_evaluations`, `evaluations_zero_trips`, and `trips_observed` distinctly.
- [ ] Prometheus query failure returns unavailable/null semantics, not zero.
- [ ] `pytest` targeted tests pass.

### Phase 6.5 - Console UI Five-State Rendering

Goal: use the backend semantic state directly in `/observability/security`.

Owned paths:

- `control-plane-ui/src/pages/GatewayGuardrails/`
- `control-plane-ui/src/services/api/`
- `control-plane-ui/src/__tests__/`

DoD:

- [ ] UI renders `No guardrail evaluations in window`.
- [ ] UI renders `0 trips after N evaluations`.
- [ ] UI renders `N trips observed`.
- [ ] UI renders stale and unavailable states unchanged from PR-3A.
- [ ] Existing AR-1 wording remains unchanged.
- [ ] Targeted vitest regression tests pass.

### Phase 6.6 - Runtime Smoke and Rollout

Goal: prove metrics in a controlled environment before production opt-in.

DoD:

- [ ] Dev/k3d smoke emits MCP allow and trip samples.
- [ ] Dev/k3d smoke emits at least one non-MCP observe-only sample.
- [ ] Prometheus query shows bounded labels only.
- [ ] `/v1/admin/gateways/metrics` returns the five semantic states in controlled scenarios.
- [ ] Production smoke remains manual operator opt-in only.

## Acceptance Criteria

| ID | Criterion | Proof |
|---|---|---|
| AC-1 | New evaluation and decision counters exist with only bounded labels. | Gateway unit tests + metrics output sample. |
| AC-2 | MCP pass and trip paths increment evaluation counters. | Gateway tests for allow/redact/flag/block. |
| AC-3 | Non-MCP proxy path emits observe-only evaluation metrics without behavior change. | Gateway tests + smoke evidence. |
| AC-4 | Control Plane API distinguishes no evaluations from evaluations with zero trips. | API tests. |
| AC-5 | UI renders five semantic states without collapsing `null` into `0`. | UI tests. |
| AC-6 | Existing PR-3A fields and legacy metric readers remain compatible. | API regression tests. |
| AC-7 | Cardinality contract remains within budget and forbidden labels are absent. | Static docs + metrics test. |

## Anti-Goals

- Do not add `tenant_id`, route, policy, tool, or raw-path labels to the new counters in the first implementation.
- Do not log or store raw payloads.
- Do not alter non-MCP request/response behavior until explicitly validated.
- Do not remove legacy metrics/readers in Phase 6 (see Compatibility Window for closure criteria).
- Do not change Security Posture or merge it with Security & Guardrails (AR-1 lock — `docs/plans/2026-05-07-observability-data-integrity.md` line 63).
- Do not create synthetic prod fallback data.

## Risks

| Risk | Severity | Mitigation |
|---|---:|---|
| Prometheus cardinality explosion | High | Start with bounded labels only; challenger must approve any richer dimensions. |
| Non-MCP guardrails accidentally change traffic behavior | High | First slice observe-only; tests prove no mutation/blocking. |
| Body handling consumes streaming request bodies | High | Limit first non-MCP scope to buffered JSON paths or explicit skip. |
| UI treats absent instrumentation as zero again | Medium | Backend semantic state + regression tests. |
| Legacy dashboards break | Medium | Additive fields only; keep old readers. |
| Security-sensitive telemetry leaks details | High | No payload labels/logs; no trace/request IDs as labels. |

## Rollback

- Gateway: feature flag the new full metrics producer if implementation adds runtime cost or risk.
- API: keep old PR-3A fields; additive fields can be hidden behind reader fallback.
- UI: fall back to PR-3A minimal wording if semantic fields are absent.
- Production: manual opt-in smoke only until dev/k3d evidence is archived.

## Test Plan

Gateway:

- `cargo fmt --check`
- `cargo test` targeted around metrics, guardrails, MCP handler, and non-MCP proxy coverage.

Control Plane API:

- targeted `pytest control-plane-api/tests/test_gateway_observability_router.py`
- targeted service tests for Prometheus reader failure and zero/null semantics.

Console UI:

- targeted vitest for guardrail card state and `/observability/security`.
- no visual golden update unless UI layout changes.

Runtime:

- dev/k3d smoke for MCP allow, MCP trip, non-MCP observe-only.
- prod smoke manual operator opt-in only.

## Open Questions For Challenger

1. Is operator `go phase 6` sufficient Q8.6 signal, or must product explicitly state `/observability/security` covers non-MCP?
2. Should non-MCP Phase 6 be observe-only first, or may it enforce redaction/blocking immediately?
3. Is the narrowed label set acceptable, even though the earlier sketch mentioned tenant/route/policy?
4. Should `flag` be a first-class decision distinct from `allow`, or should sensitive-but-allowed outcomes map to `allow` with a separate trip counter?
5. Is `ws_proxy` in scope for first non-MCP coverage, or should Phase 6.3 start with HTTP proxy only?
6. Should OPA remain config-only, or should OPA runtime counters be added in a separate later contract?

## Go / No-Go Criteria

Go if:

- External challenger validates the Q8.6 launch signal and metric label set.
- Council passes if required.
- First implementation PR is test-first and scoped to one phase.

No-Go if:

- The challenger requires product confirmation not yet provided.
- Cardinality review rejects the label set.
- Non-MCP guardrails require behavior changes that are not explicitly accepted.
- The work tries to combine all gateway/API/UI changes in one large PR.
