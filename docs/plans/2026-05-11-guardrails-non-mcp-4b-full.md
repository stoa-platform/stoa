---
id: plan-2026-05-11-guardrails-non-mcp-4b-full
triggers: [a, b]
validation_status: validated
challenge_ref: docs/decisions/2026-05-11-guardrails-non-mcp-4b-full.md
source_plan_ref: docs/plans/2026-05-09-observability-data-visibility.md
source_decision_ref: docs/decisions/2026-05-09-observability-data-visibility.md
launch_signal: "Operator requested go phase 6 on 2026-05-11; maps to Q8.6 explicit signal to open the separate MEGA."
amendments_applied: [A1, A2, A3, A4, A5, A6, A7, A8, A9, A10, A11, A12, A13, A14, A15, A16, A17, A18, A19, A20, E1, E2, E3, E4, E5, E6]
council_s2_score: 8.0
council_s2_verdict: go
impact_score: HIGH
council_review_required: true
validated_at: 2026-05-11
validation_rounds: 3
---

# Plan - Phase 6 Guardrails Non-MCP + 4B-Full

## Decision Gate

This plan matches HLFH Decision Challenge triggers:

- `a`: estimated work is greater than 5h.
- `b`: it changes product-facing observability semantics for `/observability/security` and Prometheus public metric contracts.

No implementation may start while `validation_status != validated`.

Required before code:

1. External non-Claude challenger verdict in `docs/decisions/2026-05-11-guardrails-non-mcp-4b-full.md`.
2. Council review (impact_score: HIGH locked in frontmatter; A20).
3. Phase ownership claim per phase (see Phase Ownership matrix below).

**E5 lock — Council gate scope**: after external challenger validation, Codex may only prepare Phase 6.0 deliverables that do NOT land implementation behavior:

- Cardinality evidence documentation (`docs/observability/gateway-metrics-cardinality.md` updates).
- Council materials (Council report scaffolding, persona inputs).
- Red-test scaffolding (failing tests for AC-1 to AC-16 in gateway / cp-api / cp-ui slices).
- A10 Surface Coverage Matrix verified with file:line anchors.

**No implementation code may merge before Council review is archived and passes the ≥ 8/10 threshold** (HEG-PAT-003 Council canonical). Phase 6.1+ implementation PRs are blocked by the Council gate independently of plan `validation_status`.

## Phase Ownership (A9 lock — claim heartbeat protocol)

Per CLAUDE.md multi-instance protocol (`.claude/claims/<ID>.json` + atomic `mkdir` lock). End-to-end ownership: whoever claims a phase finishes it.

| Phase | Component owner | Claim path |
|---|---|---|
| 6.0 | platform | `.claude/claims/phase-6-0-validation.json` |
| 6.1 | gateway | `.claude/claims/phase-6-1-gateway-metrics.json` |
| 6.2 | gateway | `.claude/claims/phase-6-2-mcp-coverage.json` |
| 6.3 | gateway | `.claude/claims/phase-6-3-nonmcp-observe.json` |
| 6.4 | cp-api | `.claude/claims/phase-6-4-api-reader.json` |
| 6.5 | cp-ui | `.claude/claims/phase-6-5-ui-states.json` |
| 6.6 | sre | `.claude/claims/phase-6-6-runtime-smoke.json` |

### A9 — Claim heartbeat and chaining rules

- **Stale definition**: a claim is stale after **2h without heartbeat update**, NOT after 2h of wall-clock task duration. A long-running test or build is not stale as long as the owner refreshes the heartbeat.
- **Heartbeat schema**: each claim JSON file MUST include `last_heartbeat_at` (RFC3339 UTC), refreshed by the owner at minimum every 1h while work is in-flight. Suggested refresh hook: pre-commit + post-test.
- **Stale auto-release**: any actor observing a claim with `now - last_heartbeat_at > 2h` may release it via atomic delete + new claim. The release event must be logged in `operations.log`.
- **Same-component chaining**: allowed only if the **previous PR is merged** OR explicitly abandoned via operator notice. A single gateway implementer covering 6.1 → 6.2 → 6.3 must close each claim after each phase PR merges before opening the next.
- **Cross-component chaining**: requires operator gate OR explicit approval from the next phase's component owner. No automatic handoff (e.g., gateway implementer cannot auto-claim 6.4 cp-api work).
- **Heartbeat absence = no implicit completion**: a phase is not done because its claim heartbeat stopped. Completion requires DoD checklist binary-passed + PR merged + verdict archived.

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
- MCP producer coverage for `allow`, `redact`, `block`, and `error` outcomes (A2 enum). Rate-limit guardrail emits via `guardrail="rate_limit"` + `decision="block"`. Sensitive-but-allowed outcomes map to `decision="allow"` unless a future plan introduces a separate signal (E4 lock — no `flag` value in Phase 6).
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

### A1 — Formal Definition of "Guardrail Evaluation"

A **guardrail evaluation** is one execution of one guardrail policy against one request context.

Precisions:

- A request with 3 policies evaluated increments `evaluations_total` by 3.
- A `disabled` policy does **not** increment `evaluations_total`.
- A `configured-but-not-applicable` policy does **not** increment `evaluations_total` (`not_applicable` is kept out of the counter — challenger A1 default lock).
- An evaluation error increments `evaluations_total` AND `decisions_total{decision="error"}` if the evaluation effectively started. If the evaluation never started (e.g., policy load failure), neither counter increments.
- `bypass` outcomes are **forbidden** as counter values. If a runtime bypass occurs (operator override, kill-switch), it must be logged separately, never as a `decisions_total` increment, because it would mask absence of evaluation.
- **A14 lock**: a skipped request body (non-JSON, oversized, streaming, or otherwise structurally not-applicable to the guardrail) does **NOT** increment `evaluations_total` or `decisions_total`. It must **NOT** be counted as `decision="allow"`. A bounded operational log or a separate skip metric may emit only if explicitly approved by a future plan amendment — never as a decision counter increment.

This definition is the single source of truth for what counts. Phase 6.1 / 6.2 / 6.3 implementations must conform.

### A13 — Producer Presence Signal (mandatory)

A counter that has never been incremented produces no Prometheus series. Without an explicit presence mechanism, an absent series can mean any of (a) zero evaluations, (b) producer not initialized, (c) wrong label set, (d) scrape broken, (e) service not scraped. Phase 6 cannot promise `no_evaluations` distinct from `metrics_unavailable` without one of:

**Option (a) — zero-initialized bounded series (recommended)**:

At startup, the gateway pre-creates every bounded series in the counter vectors with value `0`:

```text
for each (deployment_mode, surface, guardrail) tuple in the A10 in-scope matrix:
    stoa_guardrails_evaluations_total{deployment_mode, surface, guardrail}.inc(0)
for each (deployment_mode, surface, guardrail, decision) tuple where decision ∈ {allow, redact, block, error}:
    stoa_guardrails_decisions_total{deployment_mode, surface, guardrail, decision}.inc(0)
```

This is bounded at 500 series ceiling (A3 budget). The cp-api reader uses series **presence** (not just `value > 0`) to distinguish `no_evaluations` from `metrics_unavailable`.

**Option (b) — bounded producer-presence gauge (alternative)**:

```text
stoa_guardrails_producer_present{deployment_mode, surface} = 1
```

Cardinality: 5 modes × 4 surfaces = 20 series. Updated at startup and on producer hot-reload, never per request.

This plan locks **option (a)** as default. Option (b) is acceptable as a fallback if option (a) is impractical for a specific producer (e.g., gateway hot-reload churn), but must be challenger-approved in a phase amendment.

### Counters

```text
stoa_guardrails_evaluations_total{deployment_mode, surface, guardrail}
stoa_guardrails_decisions_total{deployment_mode, surface, guardrail, decision}
```

### A2 — Decision Taxonomy Lock

| Label | Values | Notes |
|---|---|---|
| `deployment_mode` | `edge-mcp`, `sidecar`, `proxy`, `shadow`, `unknown` | Bounded ADR-024 mode projection. |
| `surface` | `mcp`, `api_proxy`, `dynamic_proxy`, `ws_proxy` | Bounded producer call-site. |
| `guardrail` | `pii`, `injection`, `prompt_guard`, `content_filter`, `rate_limit` | Bounded feature enum. |
| `decision` | `allow`, `redact`, `block`, `error` | Bounded outcome enum (A2 challenger lock). |

Forbidden / excluded decision values (must never appear as counter labels):

- `not_applicable` — kept out of counter per A1 (policy didn't apply).
- `bypass` — runtime overrides logged separately, never as decision (would mask missing evaluation).
- `flag` — sensitive-but-allowed outcomes map to `decision=allow` with a guardrail-specific severity logged out-of-band (or open a separate plan if `flag` is product-required).
- `rate_limited` — rate-limiting maps to `guardrail=rate_limit` + `decision=block` (no separate decision value).

### A3 — Cardinality Lock (verified in Phase 6.0)

Cardinality budget under bounded labels only:

```text
evaluations_total <= 5 modes * 4 surfaces * 5 guardrails = 100 series
decisions_total <= 5 modes * 4 surfaces * 5 guardrails * 4 decisions = 400 series
```

Forbidden labels (no exceptions without challenger amendment + cardinality review):

- `tenant_id`, `tenant` (high cardinality) — unless tenant-class or hashed-tenant with bounded enum is explicitly accepted.
- `route` raw — only normalized route templates (e.g., `/v1/apis/:id`), never raw paths with IDs / query params / user input.
- `policy_id`, `policy_name` raw — only bounded policy enum if exposed.
- `tool`, `trace_id`, `span_id`, `request_id`, `user_id`, `consumer`, raw `path`, raw `url`, any payload-derived label.

Route normalization rule (lock): produce templates from FastAPI / axum route patterns; never insert path segments captured at runtime.

The prior sketch in `docs/plans/2026-05-09-observability-data-visibility.md` mentioned `{mode, tenant, route, policy}`. This plan intentionally starts narrower because `tenant_id`, route, and policy labels are limited or owner-approved under `docs/observability/telemetry-contract.md` and `docs/observability/gateway-metrics-cardinality.md`.

If tenant-scoped drilldown is required, it should come from server-side filtered traces/logs or an explicitly challenged follow-up contract, not from this first Prometheus counter set.

## A10 — Surface Coverage Matrix

Explicit mode × surface × guardrail-applicability matrix. Vague language like "extend to non-MCP" is rejected: each surface must declare in/out status and rationale.

| mode | surface | path | guardrail applicable? | `evaluations_total` emitted? | `decisions_total` emitted? | reason if excluded |
|---|---|---|---|---|---|---|
| `edge-mcp` | `mcp` | `stoa-gateway/src/mcp/handlers.rs` | yes | yes (Phase 6.2) | yes (Phase 6.2) | — |
| `proxy` | `api_proxy` | `stoa-gateway/src/proxy/api_proxy_handler.rs` | yes (PII / injection / prompt_guard / content_filter / rate_limit applicable on buffered JSON request body) | yes — observe-only first (Phase 6.3) | yes — observe-only first (Phase 6.3) | — |
| `proxy` | `dynamic_proxy` | `stoa-gateway/src/proxy/dynamic.rs` | yes (same as `api_proxy` for JSON paths) | yes — observe-only first (Phase 6.3) | yes — observe-only first (Phase 6.3) | — |
| `proxy` | `ws_proxy` | `stoa-gateway/src/ws/proxy.rs` | **conditional** — only if payload semantics are safe and bounded (no streaming-body consumption, no per-frame eval) | conditional — Phase 6.3 deliverable lists explicit gating | conditional — Phase 6.3 deliverable lists explicit gating | streaming consumption + per-frame cost = open question, Q5 in plan |
| `sidecar` | n/a | — | deferred | no (out of scope) | no (out of scope) | sidecar deployment mode (ADR-024 Q2 target) not yet shipped; no producer call-sites exist in current code |
| `connect` | n/a | — | deferred | no | no | `stoa-connect` agent bridges third-party gateways (ADR-057); guardrails not yet defined for that surface |
| `shadow` | n/a | — | deferred | no | no | shadow mode deferred per ADR-024 |
| n/a | health/readiness | `/healthz`, `/readyz` | no | no | no | not user traffic; no policy applicable |
| n/a | static admin routes | `/admin/*`, `/metrics`, `/openapi.json` | no | no | no | not subject to guardrails; auth handled at routing layer |
| n/a | internal control-plane calls | gateway → cp-api callbacks | no | no | no | internal trust boundary; no end-user payload |

Phase 6.3 implementation must reproduce this matrix in `docs/observability/gateway-metrics-cardinality.md` with verified file:line anchors before merge.

Rationale for excluded modes: a Prometheus counter that never increments is preferable to a label series that pollutes cardinality budgets with always-zero values. Re-inclusion requires a separate plan amendment.

## API Contract

Extend `GET /v1/admin/gateways/metrics?range=<range>` guardrails block with additive fields (A4 + A6 lock — distinct timestamp dimensions, state derived backend-side):

```ts
{
  guardrails: {
    state:
      | "metrics_unavailable"
      | "no_evaluations"
      | "evaluations_zero_trips"
      | "trips_observed"
      | "stale_data",
    evaluations_count: number | null,
    decisions_count: number | null,
    trips_count: number | null,                // A16: sum decisions where decision ∈ {redact, block}; excludes error
    error_count: number | null,                // A16: sum decisions where decision = "error"
    last_evaluation_delta_at: string | null,   // RFC3339 UTC — most recent positive increase of evaluations_total
    last_decision_delta_at: string | null,     // RFC3339 UTC — most recent positive increase of decisions_total
    scrape_sample_at: string | null,           // RFC3339 UTC — latest successful Prometheus sample for the series
    source_healthy: boolean,                   // Prom query succeeded AND scrape_sample_at within freshness threshold
    stale_reason: StaleReason | null,           // E6 lock — bounded enum, never raw Prometheus error
    by_guardrail: Record<
      "pii" | "injection" | "prompt_guard" | "content_filter" | "rate_limit",
      {
        state:
          | "metrics_unavailable"
          | "no_evaluations"
          | "evaluations_zero_trips"
          | "trips_observed"
          | "stale_data",
        evaluations_count: number | null,
        decisions_count: number | null,
        trips_count: number | null,             // A16: redact + block, excludes error
        error_count: number | null,             // A16: error subtotal per guardrail
        last_evaluation_delta_at: string | null,
        last_decision_delta_at: string | null,
        scrape_sample_at: string | null,        // A17: per-guardrail scrape health
        source_healthy: boolean,                // A17: per-guardrail health verdict (one card may be stale while another is healthy)
        stale_reason: StaleReason | null        // A17 + E6: per-guardrail bounded enum
      }
    >
  }
}
```

### A15 — State Precedence Order (mandatory for backend, tested in Phase 6.4)

When multiple state conditions could match, the backend MUST evaluate in this order and ship the FIRST matching state. UI never resolves precedence — it renders `state` verbatim (A6).

```text
1. metrics_unavailable
   - Prometheus query failed, Prometheus unavailable,
     OR producer presence cannot be established
     (no A13 zero-init series AND no producer_present gauge).
   - counts = null
   - source_healthy = false

2. stale_data
   - Prometheus query succeeded AND producer presence exists
   - scrape_sample_at is non-null
   - now - scrape_sample_at > freshness_threshold(range)  // A5 capped at 60 min
   - source_healthy = false

3. no_evaluations
   - source_healthy = true
   - producer presence established (A13)
   - evaluations_count = 0

4. evaluations_zero_trips
   - source_healthy = true
   - evaluations_count > 0
   - trips_count = 0
   - (error_count may be > 0 — see A16; errors are not trips)

5. trips_observed
   - source_healthy = true
   - trips_count > 0
```

State precedence applies independently to top-level `state` and each `by_guardrail` `state`. Per A17, each `by_guardrail` entry carries its own `scrape_sample_at` / `source_healthy` / `stale_reason` so the per-guardrail verdict cannot be falsified by an aggregate top-level value.

**E3 lock — top-level aggregation rule**: top-level `guardrails.state` summarizes aggregate usable signals across in-scope guardrails. A single per-guardrail stale/unavailable verdict does **NOT** automatically flip the top-level state if other in-scope guardrails are healthy. Per-guardrail states remain authoritative for card-level health. Top-level `metrics_unavailable` or `stale_data` applies only when the aggregate producer/query health cannot support a truthful aggregate verdict (e.g., Prometheus itself unreachable, or all in-scope guardrails are stale/unavailable). Phase 6.4 tests must cover: "one guardrail stale, others healthy" → top-level NOT `stale_data`; "all guardrails stale" → top-level `stale_data`.

### A16 — `trips_count` Formula and `error_count` Handling

**Formula lock**:

```text
trips_count = sum(decisions_total{decision="redact"}) + sum(decisions_total{decision="block"})
error_count = sum(decisions_total{decision="error"})
```

`decision="error"` is **NOT** a trip. It surfaces via `error_count`. Mixing evaluation incidents with security decisions in `trips_count` would corrupt the UI wording "N trips observed". `error_count > 0` while `trips_count = 0` is a legitimate observable state (e.g., upstream policy service flaking) that the UI may render distinctly in a future enhancement; Phase 6 surfaces it but does not yet design a dedicated 6th state for it.

### E6 — `stale_reason` Bounded Enum (Council S2 Pr1nc3ss lock)

`stale_reason` is **NOT** a free-form string. It is a bounded enum to prevent leaking internal infrastructure details (Prometheus hostnames, internal URLs, raw error traces) to UI consumers and through them to attackers via DOM/network inspection.

```ts
type StaleReason =
  | "prom_unreachable"      // Prometheus query failed (connection refused, timeout, 5xx)
  | "scrape_gap"            // Prometheus query succeeded but scrape_sample_at older than freshness_threshold
  | "producer_absent"       // No A13 series presence found AND no producer_present gauge
  | "stale_unknown"         // Fallback when health verdict cannot be derived to a specific reason
```

Backend mapping rules (Phase 6.4 implementation):

- Map specific Prometheus errors to `prom_unreachable` ; never pass through raw error message strings.
- Map scrape lag detection to `scrape_gap`.
- Map A13 presence-check failure to `producer_absent`.
- Use `stale_unknown` only when the underlying signal does not match any of the three specific reasons (should be rare).

UI may render the reason as a user-friendly label (e.g., "Source unreachable", "Stale scrape", "Producer offline") but **MUST NOT** display the raw enum value verbatim in messages exposed to non-privileged users.

Compatibility rules:

- Existing PR-3A fields remain unchanged.
- Existing legacy counters remain readable during the compatibility window.
- `null` remains unknown/unavailable/no sample, never fake zero.
- `0` means the backend can prove the count over the selected range.
- `state` is derived server-side. **UI MUST NOT re-derive `state` from raw counts or timestamps** (A6 lock). UI renders backend `state` verbatim. The frontend cannot decide alone whether `null` means `no_evaluations`, `metrics_unavailable`, or `stale_data`.

### A4 — Timestamp Field Semantics (A4 lock, supersedes F1)

| Field | Definition |
|---|---|
| `last_evaluation_delta_at` | `max(timestamp WHERE increase(stoa_guardrails_evaluations_total[step]) > 0)` over the selected range, RFC3339 UTC. `null` if no positive delta observed. |
| `last_decision_delta_at` | `max(timestamp WHERE increase(stoa_guardrails_decisions_total[step]) > 0)` over the selected range, RFC3339 UTC. `null` if no positive delta observed. |
| `scrape_sample_at` | Timestamp of latest successful Prometheus sample for the series/query, regardless of delta value. RFC3339 UTC. `null` if Prometheus query failed or returned no series. |
| `source_healthy` | `true` iff Prometheus query succeeded AND `scrape_sample_at` is within the freshness threshold (see A5). `false` otherwise. |

Rationale: a counter with `delta=0` over a window can mean any of (a) no evaluations, (b) healthy scrape but no traffic, (c) scrape broken, (d) misfiltered query, (e) counter reset, (f) counter exists but not for this label set. The four-field split lets the backend express these distinctions without forcing UI inference.

### A5 — `stale_data` Freshness Threshold (A5 lock, supersedes F1 formula)

Server-derived threshold with explicit cap (no formula yields > 60 min):

```text
freshness_threshold(range):
  if range <= 1h:        max(2 * scrape_interval, 5 min)
  elif range <= 24h:     max(2 * scrape_interval, 10 min)
  else  (range > 24h):   max(2 * scrape_interval, 30 min)
  cap: never exceed 60 min regardless of range
```

`state = "stale_data"` triggers (E1 lock — subordinate to A15 precedence): after A15 precedence is applied, `stale_data` triggers **only** when Prometheus query succeeded, producer presence exists (A13), `scrape_sample_at` is non-null, AND `now - scrape_sample_at > freshness_threshold(range)`. **Prometheus query failure is `metrics_unavailable`, not `stale_data`** (A15 precedence #1 wins over #2).

Default scrape interval = 30s. For ranges ≤ 1h → effective threshold = 5 min. For 7d range → effective threshold = 30 min (not 14h as in the uncapped F1 formula).

UI renders `state` as shipped. Backend owns the freshness verdict.

## Compatibility Window (A7 lock, expands F2)

Legacy guardrail counters remain readable during the compatibility window:

- `stoa_guardrails_pii_detected_total`
- `stoa_guardrails_injection_blocked_total`
- `stoa_guardrails_content_filtered_total`
- `stoa_prompt_guard_detected_total`
- rate-limit counters

Window closes only when **all five** conditions hold (A7 expansion — `prometheus_engine_queries_total` alone is insufficient):

1. **Phase 6.6 smoke prod archived (A19 lock — safe states only)** — production smoke validates the states reachable without degrading telemetry: `evaluations_zero_trips` and/or `trips_observed`, plus bounded-label evidence. `metrics_unavailable`, `no_evaluations`, and `stale_data` are validated separately in dev/k3d or staging via controlled fault injection; production fault injection is forbidden unless separately approved by SRE in a dedicated chaos-injection plan. Archive prod smoke under `docs/audits/<YYYY-MM-DD>-phase-6-rollout/findings.md`.
2. **14 days without legacy cp-api field consumers** — verified by API access logs / dashboard queries / internal script audit (not just Prometheus engine stats). cp-api fields surfaced by PR-3A that map to legacy counters must show zero reads.
3. **14 days without legacy PromQL consumers observed where observable** — Prometheus query-stats audit (`prometheus_engine_queries_total{query=~".*stoa_guardrails_(pii_detected|injection_blocked|content_filtered)_total.*"}`) shows zero non-canary reads. Explicit caveat: this metric **does not catch** Grafana dashboards via external Prometheus, ops scripts hitting Prometheus directly, bookmarks / exports outside the measured engine.
4. **Release note / migration note published** — internal release notes + customer-facing changelog if any external consumer exists, naming the legacy counters being deprecated and the replacement counters.
5. **Legacy removal plan exists separately** — new plan opened post-window, naming legacy counters to remove, removal rollback steps, and re-introduction criteria if a forgotten consumer surfaces.

Legacy counter removal is scheduled by that **separate plan**. Phase 6 does **not** remove legacy counters under any condition (binding anti-goal). The 14-day floor is challenger-revisable upward if downstream dashboards or partner integrations are identified during conditions 2–3.

## Phases

### Phase Dependency Graph (A8 lock — 6.4 is backend-only)

**Phase 6.4 scope clarification (A8)**: Phase 6.4 = `Control Plane API Reader` covers ONLY the backend/API contract (cp-api reads new counters, derives the 5 states, exposes via `/v1/admin/gateways/metrics`). It does **NOT** include UI smoke, console-visible behavior, or end-to-end user experience validation. Those are Phase 6.5 (UI rendering) and Phase 6.6 (runtime smoke). Per A8 conditional: because 6.4 is strictly backend, 6.4 may start after 6.2 alone, not requiring 6.3.

```
6.0 (validation) ─→ 6.1 (gateway metrics) ─┬─→ 6.2 (MCP coverage)  ──→ 6.4 (cp-api backend reader) ─→ 6.5 (UI states) ─→ 6.6 (prod smoke)
                                            └─→ 6.3 (non-MCP obs) ───────────┘
                                              (parallel after 6.1, both feed 6.5 evidence)
```

Rules:

- **6.0 → 6.1**: validation must finish before producer code lands. Phase 6.0 DoD locks contract + cardinality + semantics (A1 + A2 + A3 + A4 + A5).
- **6.1 → {6.2, 6.3}**: 6.1 ships the counter contract on the producer side; 6.2 and 6.3 are independent call-site instrumentations and may run in parallel after 6.1.
- **6.2 → 6.4**: 6.4 starts when 6.2 has shipped (cp-api unit tests rely on MCP `allow`/`redact`/`block`/`error` samples). 6.3 may still be in flight; the cp-api reader is agnostic to which call-sites produce, because 6.4 is backend-only.
- **{6.4, 6.3} → 6.5**: UI strictly requires (a) 6.4 cp-api fields shipped and (b) 6.3 non-MCP producer shipped, because the UI surfaces non-MCP traffic distinctly. UI work cannot begin until both predecessors are complete.
- **6.5 → 6.6**: prod smoke validates the full stack with UI present, runs last.

A phase may not be marked complete until all its predecessors are complete and its DoD is binary-checked.

### Phase 6.0 - Validation and Red Tests

Goal: lock the contract before implementation.

Deliverables:

- This plan transitions from `draft` to `validated` via the multi-round external challenger flow (HEG-PAT-022).
- A small SPEC addendum may be created if the branch root `SPEC.md` is replaced by a ticket-specific spec in the implementation branch; current root `SPEC.md` belongs to an older CAB and must not be reused silently.
- Failing tests are added for the accepted acceptance criteria before production code changes.

DoD (A3 — cardinality / contract / semantics locked here, before any gateway code):

- [ ] External challenger verdict = `validated` archived in `docs/decisions/2026-05-11-guardrails-non-mcp-4b-full.md`.
- [ ] Council score meets the required threshold if impact score is HIGH or above.
- [ ] Red tests exist in gateway, API, and UI slices before corresponding implementation.
- [ ] **Cardinality budget documented** in `docs/observability/gateway-metrics-cardinality.md`: max series estimate from the A2 enum table (100 + 400 = 500 series ceiling), with the forbidden-labels list reproduced verbatim.
- [ ] **Route normalization rule documented**: only FastAPI / axum-resolved route templates may serve as `route` label values (if `route` is ever added in a future plan amendment). Raw path / query / user-input forbidden.
- [ ] **Label enums listed** with the A2 lock (`decision ∈ allow | redact | block | error`; `not_applicable` / `bypass` / `flag` / `rate_limited` excluded with rationale).
- [ ] **Reviewer authority confirmed**: reviewer (Claude or Council) may reject any unbounded label introduction without operator escalation.
- [ ] **A10 Surface Coverage Matrix reproduced** in cardinality doc with verified file:line anchors for in-scope surfaces (mcp / api_proxy / dynamic_proxy / conditional ws_proxy).

### Phase 6.1 - Gateway Metric Contract

Goal: add producer-side counters with bounded labels.

Owned paths:

- `stoa-gateway/src/metrics.rs`
- `stoa-gateway/src/guardrails/`
- targeted gateway tests
- `docs/observability/gateway-metrics-cardinality.md`

DoD (A13 lock — producer presence):

- [ ] `stoa_guardrails_evaluations_total` and `stoa_guardrails_decisions_total` are exported by `/metrics`.
- [ ] **Producer presence implemented per A13 option (a)**: at startup the gateway pre-initializes zero-valued series for every bounded `(deployment_mode, surface, guardrail)` tuple in the A10 in-scope matrix AND every `(deployment_mode, surface, guardrail, decision)` tuple where `decision ∈ {allow, redact, block, error}`. Total bounded series count ≤ A3 budget (≤ 500).
- [ ] **Producer presence test**: a fresh scrape against a freshly-started gateway with **zero traffic** returns enough zero-valued series for cp-api to distinguish `no_evaluations` from `metrics_unavailable`. Test executes the `/metrics` endpoint pre-traffic and asserts presence of all bounded series with value `0`.
- [ ] Option (b) fallback (`stoa_guardrails_producer_present` gauge) only if (a) is impractical, documented with operator approval.
- [ ] Unit tests prove the new metrics do not include forbidden labels (A3 list).
- [ ] Legacy counters continue to emit for compatibility (A7 window).
- [ ] `cargo fmt --check` and `cargo test` pass locally.

### Phase 6.2 - MCP Coverage

Goal: instrument MCP tool-call guardrail pass and trip paths.

Owned paths:

- `stoa-gateway/src/mcp/handlers.rs`
- `stoa-gateway/src/guardrails/`
- targeted gateway tests

DoD (A2 lock — decision taxonomy `allow | redact | block | error`):

- [ ] A clean MCP request increments `evaluations_total` AND `decisions_total{decision="allow"}` for every applicable guardrail policy (A1 definition).
- [ ] PII redact path increments `evaluations_total` AND `decisions_total{decision="redact", guardrail="pii"}`.
- [ ] Injection block path increments `evaluations_total` AND `decisions_total{decision="block", guardrail="injection"}`.
- [ ] Content filter block path increments `evaluations_total` AND `decisions_total{decision="block", guardrail="content_filter"}`.
- [ ] Rate-limit block path increments `evaluations_total` AND `decisions_total{decision="block", guardrail="rate_limit"}` (no separate `decision="rate_limited"` — A2 lock).
- [ ] Evaluation error path (policy started but failed) increments `evaluations_total` AND `decisions_total{decision="error"}` (A1 + A2).
- [ ] `disabled` and `not_applicable` policies do **not** increment counters (A1 + A2 explicit exclusion).
- [ ] Existing legacy trip counters still increment as before (compatibility window — A7).

### Phase 6.3 - Non-MCP Observe-Only Coverage

Goal: evaluate guardrails on non-MCP traffic without mutating or blocking traffic in the first implementation slice.

**E2 lock — decision semantics in observe-only**: for non-MCP observe-only surfaces, `decisions_total{decision=...}` records the guardrail policy outcome that **would have applied under enforcement**. It does **NOT** imply traffic was mutated, redacted, or blocked. Phase 6.3 must preserve request/response behavior bit-for-bit. A `decision="block"` increment on `api_proxy` means "policy verdict was block" — the request still completed normally. Enforcement of non-MCP guardrails requires a separate follow-up plan.

Candidate paths to confirm during implementation:

- `stoa-gateway/src/proxy/api_proxy_handler.rs`
- `stoa-gateway/src/proxy/dynamic.rs`
- `stoa-gateway/src/ws/proxy.rs` only if payload semantics are safe and bounded

DoD (A10 — surface coverage matrix conformance):

- [ ] `api_proxy` (`stoa-gateway/src/proxy/api_proxy_handler.rs`) emits `evaluations_total` and `decisions_total` per A1 definition, in observe-only mode (no request/response mutation, no blocking).
- [ ] `dynamic_proxy` (`stoa-gateway/src/proxy/dynamic.rs`) emits per the same observe-only contract.
- [ ] `ws_proxy` (`stoa-gateway/src/ws/proxy.rs`) explicit gating decision archived: either (a) in-scope with payload bounding rules documented and tested, or (b) deferred with a follow-up plan reference. No half-measure.
- [ ] Body handling never consumes streaming request bodies. Non-JSON, oversized, streaming, or otherwise structurally not-applicable bodies are skipped **WITHOUT** incrementing `evaluations_total` or `decisions_total` (A14 lock — never `decision="allow"` for skipped bodies). A bounded operational log or separate skip metric may be added only via future plan amendment.
- [ ] No request/response behavior changes for non-MCP traffic in this slice. Confirmed by integration tests that diff request/response headers + status before/after instrumentation.
- [ ] `docs/observability/gateway-metrics-cardinality.md` updated with verified file:line anchors for each surface, matching the A10 matrix.

### Phase 6.4 - Control Plane API Reader (backend contract only — A8)

Goal: expose the semantic split without breaking PR-3A fields. **No UI work in this phase** (A8 — backend contract only; UI = Phase 6.5).

Owned paths:

- `control-plane-api/src/services/gateway_metrics_service.py`
- `control-plane-api/tests/test_gateway_observability_router.py`
- schemas only if the router already uses explicit response models

DoD (A4 + A5 + A6 + A15 + A16 + A17 lock):

- [ ] API reads new `evaluations_total` and `decisions_total` counters.
- [ ] API continues reading legacy trip counters during compatibility window (A7).
- [ ] API computes and ships `state ∈ {metrics_unavailable, no_evaluations, evaluations_zero_trips, trips_observed, stale_data}` **server-side** per A6. UI cannot derive `state`.
- [ ] **A15 state precedence implemented and tested**: cp-api evaluates the 5 states in the locked order (`metrics_unavailable` → `stale_data` → `no_evaluations` → `evaluations_zero_trips` → `trips_observed`) and ships the first match. Unit tests cover each boundary transition.
- [ ] **A15 producer presence used**: distinguishing `no_evaluations` from `metrics_unavailable` uses A13 series-presence check (or `producer_present` gauge if A13 option (b)), NOT just `count == 0`.
- [ ] **A16 `trips_count` and `error_count` formulas**: `trips_count = sum(redact) + sum(block)`, `error_count = sum(error)`. Tests assert error never contributes to trips_count; redact+block+error scenario produces `trips=redact+block` and `error_count=error` separately.
- [ ] API ships all four A4 timestamp fields: `last_evaluation_delta_at`, `last_decision_delta_at`, `scrape_sample_at`, `source_healthy`.
- [ ] `stale_data` triggers conform to A5 capped freshness threshold (`≤ 60 min` floor regardless of range).
- [ ] Prometheus query failure returns `state="metrics_unavailable"` + `null` counts + `source_healthy=false`, never `0`.
- [ ] **A17 per-guardrail health fields**: each `by_guardrail` entry ships its own `scrape_sample_at`, `source_healthy`, `stale_reason`. Test scenario: one guardrail stale, others healthy — verify per-card verdicts independent of top-level aggregate.
- [ ] `by_guardrail` map ships per-guardrail `state` independently (one guardrail may be `stale_data` while another is `evaluations_zero_trips`).
- [ ] `stale_reason` is populated whenever `state="stale_data"` and conforms to **E6 bounded enum** (`prom_unreachable` | `scrape_gap` | `producer_absent` | `stale_unknown`). Test: `stale_reason` never contains raw Prometheus error messages, hostnames, internal URLs, or query traces.
- [ ] `pytest` targeted tests pass, including: state transitions, `null` vs `0` distinction, threshold cap (7d range → ≤ 60 min stale window), per-guardrail independence, trips_count/error_count separation, **E6 stale_reason enum validation** (forbidden raw error string regression test).

### Phase 6.5 - Console UI Five-State Rendering

Goal: use the backend semantic state directly in `/observability/security`. UI **renders** state, never derives it (A6 lock).

Owned paths:

- `control-plane-ui/src/pages/GatewayGuardrails/`
- `control-plane-ui/src/services/api/`
- `control-plane-ui/src/__tests__/`

DoD (A6 + A11 lock):

- [ ] UI renders the 5 server-shipped states directly from `state`:
  - `metrics_unavailable` → "Metrics unavailable" wording (PR-3A baseline).
  - `no_evaluations` → "No guardrail evaluations in window".
  - `evaluations_zero_trips` → "0 trips after N evaluations" (substitute N from `evaluations_count`).
  - `trips_observed` → "N trips observed" (substitute N from `trips_count`).
  - `stale_data` → "Data stale (last observed: <timestamp>)" using `last_evaluation_delta_at` or `scrape_sample_at` for display only — **not for state recomputation** (A6).
- [ ] UI must NOT collapse `null` count fields into `0`. `null` → render baseline wording for the corresponding state, never "0".
- [ ] **A11 AR-1 anti-regression test** added to `control-plane-ui/src/__tests__/`:
  - `/security-posture` page title + subtitle MUST match AR-1 canonical wording: "Compliance findings, security score, configuration assessment" (verified by snapshot or text match test).
  - `/observability/security` page title + subtitle MUST match AR-1 canonical wording: "Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring".
  - Test fails if either page subtitle is changed, even by a single word, without an explicit AR-1 amendment plan.
- [ ] Navigation / sidebar / IA NOT changed by Phase 6.5 (AR-1 lock — no fusion of Security Posture and Security & Guardrails).
- [ ] Targeted vitest regression tests pass, including 5-state rendering matrix + AR-1 anti-regression test.

### Phase 6.6 - Runtime Smoke and Rollout

Goal: prove metrics in a controlled environment before production opt-in.

DoD (A12 lock — no real PII / no real customer prompt content):

**Dev/k3d smoke (all 5 states tested here, A19 lock)**:

- [ ] Dev/k3d smoke emits MCP `allow`, `redact`, `block`, `error` samples (A2 enum complete).
- [ ] Dev/k3d smoke emits at least one non-MCP `api_proxy` or `dynamic_proxy` observe-only sample.
- [ ] Prometheus query shows bounded labels only (A3 forbidden-labels list verified absent).
- [ ] **A13 producer presence verified**: scrape against freshly-started gateway with zero traffic returns bounded zero-valued series sufficient for cp-api to distinguish `no_evaluations` from `metrics_unavailable`.
- [ ] **A18 lock**: `/v1/admin/gateways/metrics` returns the five `state` values in dev/k3d controlled scenarios (NOT tenant-scoped — A3 forbids tenant labels):
  - `metrics_unavailable` via stopped Prometheus.
  - `no_evaluations` via **clean dev/k3d environment or isolated synthetic gateway instance** before emitting any guardrail-applicable traffic (NOT via tenant filter — Phase 6 has no tenant label).
  - `evaluations_zero_trips` via clean traffic (allow-only).
  - `trips_observed` via deterministic fixture trip.
  - `stale_data` via controlled scrape-pause injection.
- [ ] AR-1 anti-regression test (A11) green in dev environment.

**Prod smoke (A12 + A19 — operator-only, safe states only)**:

- [ ] **A19 lock**: prod smoke validates only safe-reachable states — `evaluations_zero_trips` and/or `trips_observed` — plus bounded-label evidence. `metrics_unavailable`, `no_evaluations`, and `stale_data` are **NOT** validated in production. Those three require fault injection (stopping Prometheus, isolating a fresh environment, pausing scrapes) which is **forbidden in production unless separately approved by SRE in a dedicated chaos-injection plan**. Dev/k3d or staging covers the unreachable states.
- [ ] `workflow_dispatch` only. No schedule trigger. No automatic firing.
- [ ] Operator opt-in is explicit (PR comment lock OR `OPERATOR_OPT_IN` env var with operator initials; not a default value).
- [ ] Synthetic tenant + synthetic route dedicated to the probe (tenant name e.g. `guardrails-probe`, never a real customer tenant).
- [ ] **No real PII in payloads**. No emails, phone numbers, credit cards, SSNs, names of real persons, or any pattern that could match a known customer record.
- [ ] **No real customer prompt content in payloads**. All test prompts are deterministic, pre-approved synthetic strings.
- [ ] Synthetic payload fixtures committed in `docs/observability/phase-6-smoke-fixtures.md` with verbatim payload examples. Operator reviews fixtures before each prod run.
- [ ] Cleanup / rollback steps documented: how to delete probe traces from OpenSearch, how to filter probe metrics from Prometheus dashboards, how to drop the synthetic tenant.
- [ ] Smoke output archived with UTC timestamp under `docs/audits/<YYYY-MM-DD>-phase-6-rollout/findings.md`, including verdict per-state and any failure mode observed.
- [ ] Audit archive references this plan + decision-log for traceability.

## Acceptance Criteria

| ID | Criterion | Proof |
|---|---|---|
| AC-1 | New `evaluations_total` + `decisions_total` counters exist with only A2 / A3 bounded labels (`decision ∈ allow|redact|block|error`). | Gateway unit tests + metrics output sample + cardinality doc. |
| AC-2 | MCP path increments `evaluations_total` per A1 definition AND `decisions_total{decision}` for `allow`, `redact`, `block`, `error`. | Gateway tests covering 4 decision values. |
| AC-3 | Non-MCP `api_proxy` + `dynamic_proxy` emit observe-only metrics matching A10 matrix; no request/response behavior change. | Gateway tests + smoke evidence + header/status diff before/after. |
| AC-4 | cp-api ships server-derived `state` (A6) with 4 distinct timestamp fields (A4) and capped freshness threshold (A5). | API tests covering 5 state values + threshold cap. |
| AC-5 | UI renders 5 states verbatim from server `state`; never collapses `null` into `0`; AR-1 anti-regression test green (A11). | UI vitest including subtitle snapshot tests. |
| AC-6 | Existing PR-3A fields and legacy metric readers remain compatible during compatibility window (A7). | API regression tests + legacy counter read tests. |
| AC-7 | Cardinality contract remains within A3 budget (≤ 500 series) and forbidden labels are absent. | Static docs + metrics linting test. |
| AC-8 | Phase 6.6 prod smoke uses synthetic fixtures only — no real PII / no real customer prompt (A12). | Audit archive + fixture diff vs known-PII patterns. |
| AC-9 | Compatibility window closes only on A7 5-condition lock + A19 prod-safe-states-only condition 1; legacy removal scheduled by separate plan, never inside Phase 6. | Window-closure checklist + separate-plan reference. |
| AC-10 | Producer presence (A13): fresh-scrape with zero traffic exposes bounded zero-valued series (option a) or producer-present gauge (option b) sufficient for cp-api `no_evaluations` ≠ `metrics_unavailable` distinction. | Gateway startup test + cp-api state precedence unit test. |
| AC-11 | Skipped bodies (A14): non-JSON, oversized, streaming, or structurally not-applicable bodies never increment `evaluations_total` or `decisions_total`. | Gateway integration test asserting counter values unchanged across skip scenarios. |
| AC-12 | State precedence (A15): cp-api evaluates 5 states in locked order (`metrics_unavailable` → `stale_data` → `no_evaluations` → `evaluations_zero_trips` → `trips_observed`); UI never overrides backend `state`. | cp-api unit tests covering boundary transitions + UI snapshot tests rendering `state` verbatim. |
| AC-13 | Counter formulas (A16): `trips_count = redact + block` (excludes `error`); `error_count = error`. Both top-level and per-guardrail. | cp-api unit tests with redact + block + error fixture scenarios. |
| AC-14 | Per-guardrail health (A17): each `by_guardrail` entry ships its own `scrape_sample_at`, `source_healthy`, `stale_reason`; one guardrail stale does not flip aggregate top-level state. | cp-api unit test: mix one stale guardrail with healthy others, assert independent verdicts. |
| AC-15 | Prod smoke safe-state restriction (A19): production validates only `evaluations_zero_trips` and `trips_observed`; `metrics_unavailable`, `no_evaluations`, `stale_data` validated in dev/k3d or staging only. | Audit archive of dev/k3d 5-state coverage + prod smoke archive with only safe states. |
| AC-16 | Council gate (A20): plan frontmatter declares `impact_score: HIGH` and `council_review_required: true`; Council review completed before code lands. | Frontmatter check + Council report archived. |
| AC-17 | `stale_reason` bounded enum (E6 Council S2 Pr1nc3ss lock): only `prom_unreachable` / `scrape_gap` / `producer_absent` / `stale_unknown`. Raw Prometheus error strings, hostnames, internal URLs never leak via this field. | cp-api unit test asserting enum membership + regression test for forbidden raw-error patterns. |

## Anti-Goals

- Do not add `tenant_id`, route, policy, tool, or raw-path labels to the new counters in the first implementation (A3 forbidden-labels list).
- Do not log or store raw payloads.
- Do not alter non-MCP request/response behavior until explicitly validated.
- Do not remove legacy metrics/readers in Phase 6 (see Compatibility Window for closure criteria — A7).
- Do not change Security Posture or merge it with Security & Guardrails (AR-1 lock — `docs/plans/2026-05-07-observability-data-integrity.md` line 63 + A11 test).
- Do not create synthetic prod fallback data.
- Do not add `flag`, `not_applicable`, `bypass`, or `rate_limited` as `decision` values (A2 taxonomy lock — only `allow | redact | block | error`).
- Do not let the UI derive `state` from raw counts or timestamps (A6 — backend owns `state` verdict).
- Do not include real PII or real customer prompt content in Phase 6.6 prod smoke payloads (A12 — synthetic fixtures only).
- Do not let a stale claim auto-release while a long-running build/test is in flight; owners must refresh heartbeat (A9).
- Do not count skipped bodies (non-JSON, oversized, streaming, not-applicable) as `decision="allow"` (A14 lock — they must not increment any counter).
- Do not require tenant-scoped `no_evaluations` validation (A18 lock) — Phase 6 has no tenant label; use clean dev/k3d env or isolated synthetic gateway instead.
- Do not validate `metrics_unavailable` / `no_evaluations` / `stale_data` in production smoke (A19 lock) — production fault injection forbidden unless SRE-approved chaos plan exists.
- Do not promise `no_evaluations` without A13 producer-presence mechanism (zero-init series or producer_present gauge). An absent series is not proof of zero traffic.
- Do not include `decision="error"` in `trips_count` (A16 lock). Errors surface via `error_count`, never via the trips wording.
- Do not leak Prometheus error details, hostnames, internal URLs, query traces, or raw error messages via `stale_reason` (E6 lock). `stale_reason` is a bounded enum; raw Prom errors stay server-side in logs.

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

Round 2 status: all 6 questions verrouillées par le challenger. Q1 et Q6 (non répondus en Round 1) sont maintenant lockés. Q2/Q3/Q4/Q5 sont confirmés sur plan complet.

| # | Question | Round 2 verdict | Lock |
|---|---|---|---|
| Q1 | Is operator `go phase 6` sufficient Q8.6 signal, or must product explicitly state `/observability/security` covers non-MCP? | **YES** | Operator `go` combine audit MCP-only + risque blind spot + demande explicite + besoin distinguer no_evaluations/zero/stale/unavailable. Q8.6 signaux #2 et #3 satisfaits. Pas besoin de confirmation produit supplémentaire, sauf arbitrage Council formel. |
| Q2 | Should non-MCP Phase 6 be observe-only first, or may it enforce redaction/blocking immediately? | **Observe-only** | Aucune enforcement non-MCP dans Phase 6 (no mutation/blocking/redaction). Enforcement = follow-up plan séparé avec Decision Gate propre. |
| Q3 | Is the narrowed label set acceptable, even though the earlier sketch mentioned tenant/route/policy? | **YES** | A3 forbidden labels list validée. Drilldown futur tenant/route/policy = plan séparé. |
| Q4 | Should `flag` be a first-class decision distinct from `allow`, or should sensitive-but-allowed outcomes map to `allow` with a separate trip counter? | **NO `flag`** | `decision ∈ allow | redact | block | error` verrouillé. Sensitive-but-allowed = `decision="allow"` + signal out-of-band non-cardinal. Future taxonomie `flag` = plan séparé. |
| Q5 | Is `ws_proxy` in scope for first non-MCP coverage, or should Phase 6.3 start with HTTP proxy only? | **Conditional, deferred par défaut** | `ws_proxy` in-scope only if Phase 6.3 prouve bounded payload semantics + no streaming-body consumption + no per-frame eval + no behavior change. Sinon deferred avec follow-up plan reference. Aucune demi-mesure. |
| Q6 | Should OPA remain config-only, or should OPA runtime counters be added in a separate later contract? | **OPA config-only** | Pas de nouveaux compteurs runtime OPA dans cette MEGA. Deferred à contrat séparé. Phase 6 peut préserver l'affichage config/state existant mais ne crée pas de runtime evaluations_total / decisions_total OPA. |

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
