# Challenger Verdict — Observability Data Visibility Audit

- **Date**: 2026-05-09
- **Challenger**: ChatGPT (external, non-Claude — per HLFH Decision Gate framework)
- **Audit ref**: [findings.md](findings.md)
- **Status**: challenged → constraints locked for plan drafting
- **Plan**: not yet drafted (awaiting operator `/go`)

## Validated by challenger

- 4-gap split holds. Avoids the "prod is empty therefore seeder is broken" trap and separates demo data, product model, infra, metric semantics.
- **Gap 3 first** (no code, cluster diag) — confirmed as priority 1.
- "No silent synthetic fallbacks in prod" principle holds. Plan must remain consistent with the recent PR train (#2730–#2745) that chose honest empty states.

## Challenges accepted (locked for plan)

### C1 — Gap 1A is a fixture, not a pipeline validation

**Decision**: rename Gap 1A to "observability fixtures for audit-log".

**Constraints locked**:
- Never enabled by default in prod.
- Each event tagged with explicit synthetic marker: `source=seed` and/or `metadata.synthetic=true`.
- UI/API must surface the synthetic indicator; never mix with real events without distinction.
- 1A **does not** prove `emit_audit_event → Kafka → consumer → audit_events → UI` end-to-end.
- End-to-end proof belongs to Gap 1B, which itself is **not** a seeder responsibility but a separate synthetic-traffic / smoke job.

### C2 — Gap 2 is compliance-sensitive, not just plumbing

**Decision**: ADR before any migration. The dual-view design must explicitly name dimensions and authorisation rules.

**ADR must cover**:
- `resource_tenant_id` (current `tenant_id`)
- `actor_subject_id` (user / service account / API token)
- `actor_home_tenant_id` or `actor_workspace_tenant_id` — only if semantics are unambiguous at request time
- Multi-tenant user case (one subject across tenants)
- Service accounts / platform-admin actors backfill rules
- `visibility_scope` and cross-tenant redaction rules to avoid leakage when a user from tenant A acts on resource of tenant B

Solution shape `actor_tenant_id` (initially proposed in audit) is rejected as ambiguous without the matrix above.

### C3 — Gap 3 cluster diagnostic must produce a traceable end-to-end probe

**Decision**: cluster diag is not just `kubectl get pods` + `_cat/indices`. It must emit a known-unique span and follow it through every hop.

**Locked sequence**:
1. Gateway env: confirm `STOA_OTEL_ENDPOINT` present in pod env.
2. Service `stoa-alloy-otlp` exists in `stoa-monitoring` and accepts OTLP gRPC.
3. Emit one tagged request through gateway on a known route (unique header/correlation id).
4. Find the span in Alloy logs/metrics.
5. Find the span in Data-Prepper pipeline output / OpenSearch index `otel-v1-apm-span-*`.
6. Find the trace via `/v1/monitoring/transactions`.
7. Verify UI time-window matches.

**Failure modes to enumerate explicitly** (none pre-eliminated): exporter not initialised, DNS, NetworkPolicy, OpenSearch mapping, UI time range, Data-Prepper pipeline misconfig, Tempo fallback inactive.

### C4 — Gap 4B cannot honestly distinguish "0 trips" from "no series" without an evaluations counter

**Decision**: split Gap 4B into two layers.

- **4B-minimal — copy/wording only**: estimate ~0.5d. Rename "No metrics sample" to a formulation that does not claim 0 vs absent (e.g. "No guardrail trip samples in window"). UI/API only.
- **4B-full — true semantic split**: estimate 1–2d (or more if gateway code touched). Requires new gateway counters that fire on every guardrail evaluation, not just on trips:
  ```
  stoa_guardrails_evaluations_total{mode, tenant, route, policy}
  stoa_guardrails_decisions_total{decision="allow|redact|block", ...}
  ```
  Then the UI can render five honest states: `metrics_unavailable` · `no_evaluations` · `evaluations_zero_trips` · `trips_observed` · `stale_data`.

Without the evaluations counter, the most honest copy is "No guardrail trip samples" — never "0 trips".

### C5 — Gap 4A blast in prod raised to moderate-high

**Decision**: severity revised. Operators using `/observability/security` as proof of guardrail coverage may be misled because a slice of traffic is not instrumented at all (only MCP path emits). Not an enforcement bug, but a security observability blind spot.

## Severity matrix — revised

| Gap | Severity (revised) | Note |
|---|---|---|
| 1 — Seeder catalog-only | demo: high · prod: low **only if gated** | Dangerous only if synthetic data leaks into prod without `source=seed` badge. |
| 2 — audit by resource vs by actor | moderate to moderate-high | Compliance-sensitive when admins expect "who did what". |
| 3 — trace pipeline | high | Diagnose before any code. |
| 4A — guardrails MCP-only | moderate-high | Security observability blind spot outside MCP. |
| 4B — null vs zero | moderate | Wording fix is fast; true semantics needs evaluations counter. |

## Sequence — locked for plan

1. **Gap 3 cluster diag** with end-to-end traceable probe (no code).
2. **Seed-vs-runtime contract decision** — short doc deciding whether seeder stays catalog-only or grows a sibling `observability_fixtures` module.
3. **Gap 1A** — fixture audit only, gated by profile, tagged synthetic. Not labelled as pipeline validation.
4. **Gap 4B-minimal** — honest wording, no semantic claim the backend cannot prove.
5. **Gap 2 ADR** — by_resource / by_actor / authorisation matrix / cross-tenant redaction.
6. **Gap 1B** — synthetic traffic / smoke job, separate from seeder core. End-to-end pipeline proof.
7. **Gap 4A + 4B-full** — separate MEGA. Add `evaluations_total` and `decisions_total` counters; extend coverage to non-MCP proxy paths.

## Answers to audit's open questions

1. **`by_actor` need**: real if `cpi-admin` or cross-tenant operators exist. Should likely be a platform/admin view with strict redaction, not a standard tenant view.
2. **Trace pipeline intent**: must be confirmed as product intent before fix. If prod is intentionally Prometheus-only until Q3, Gap 3 reduces to UI/copy/config; otherwise Gap 3 is highest priority.
3. **AR-1 contract**: incomplete. Missing distinctions: `no_evaluations`, `evaluated_zero_trips`, `series_absent`, `metrics_unavailable`.
4. **Seeder scope**: should not generate runtime data by default. Explicit, tagged fixtures in `demo`/`staging`/`dev` profiles only. Synthetic traffic lives in a separate smoke/probe.
5. **Guardrails instrumentation**: at the layer where policy is evaluated. Gateway-wide if policy is gateway-wide; per-protocol if each protocol has its own evaluator. Current MCP-only model is acceptable only if the product explicitly states "guardrails observability is MCP-only".

## Locked decisions before `/go`

- Gap 3 first, no code.
- Gap 1A = audit fixture, not pipeline validation. Forbidden in prod by default. Tagged synthetic.
- Gap 4B-minimal = honest wording only. Gap 4B-full = new evaluations counter (separate work).
- Gap 2 routes through ADR before any migration.
- Gap 4A leaves the observability batch and ships in its own MEGA, bundled with 4B-full.

## Next step

Operator `/go` triggers plan drafting against the locked sequence and constraints above.
The plan will be filed at `docs/plans/2026-05-09-observability-data-visibility.md` with `validation_status: draft`, then re-challenged before execution by Codex.
