# Observability Data Visibility — Audit

- **Date**: 2026-05-09
- **Scope**: Why observability surfaces (`/audit-log`, `/observability/live-calls`, `/observability/security`) feel empty in prod despite the seeder running, and what fix each surface actually needs.
- **Trigger**: Operator report that the seeder runs but logs / traces / runtime data are not visible end-to-end.
- **Status**: Discovery. No code change. Intended for external challenger (ChatGPT) review before plan drafting.

## Verdict

The seeder is not broken. It does what it was scoped to do (catalog bootstrap). The gap is structural: **all four observability surfaces depend on runtime data sources that are either not seeded, only partially wired in prod, or have legitimate empty states the operator misreads as "broken".**

Four distinct gaps, only one of which is a true regression candidate; the others are scope/coverage decisions that should be ticketed and challenged before any code is written.

## Method

| Layer | What was inspected |
|---|---|
| Seeder | `control-plane-api/scripts/seeder/profiles/{dev,staging,prod}.py`, `scripts/seeder/steps/` |
| Audit pipeline | `kafka_service.emit_audit_event` call sites; `workers/audit_trail_consumer.py`; `routers/audit.py`; `models/audit_event.py`; alembic `044_create_audit_events.py` |
| Live Calls (Prom) | `control-plane-ui/src/pages/CallFlow/metrics.ts`; `hooks/usePrometheus.ts`; gateway metrics registry `stoa-gateway/src/metrics.rs` |
| Traces | `control-plane-api/src/routers/monitoring.py`; `services/{tempo_service,monitoring_service}.py`; `stoa-gateway/src/telemetry/mod.rs`; `charts/stoa-platform/values-prod.yaml` |
| Guardrails | `stoa-gateway/src/metrics.rs` (registry + helpers); `stoa-gateway/src/mcp/handlers.rs` (call sites); `routers/gateway_observability.py` |
| Prior verifications | `docs/audits/2026-05-08-live-calls-runtime-verification/findings.md`; `2026-05-09-audit-log-runtime-verification/findings.md`; `2026-05-09-guardrails-runtime-verification/findings.md` |

No cluster `kubectl` was run for this audit. Anything labelled "to confirm on cluster" below is the boundary of code/config inspection.

## Recently delivered (context)

The PR train just merged (2026-05-07 → 2026-05-09) explicitly chose **honest empty states over synthetic fallbacks**:

- PR #2726 — audit consumer implementation
- PR #2730 — `STOA_AUDIT_DEMO_FALLBACK` defaults `false` in prod
- PR #2737/#2738 — audit `/stats`, `/actions`, actor resolution, demo fallback gate
- PR #2740 — live-calls aligned on `http_route` (drop `path`)
- PR #2741/#2742/#2743 — guardrails 5-state truth contract + UI
- PR #2745 — observability nav IA cleanup

Verdict from those audits: each surface, **on its own contract**, passes. The operator-perceived emptiness is a level above (system-of-systems), not a regression of any of those PRs.

---

## Gap 1 — Seeder is catalog-only

**Code**

```text
control-plane-api/scripts/seeder/profiles/dev.py:5-13
  STEPS = [tenants, gateway, apis, plans, consumers, mcp_servers, security_posture]
control-plane-api/scripts/seeder/steps/
  apis.py  consumers.py  gateway.py  mcp_servers.py  plans.py
  prospects.py  security_posture.py  tenants.py
```

No `audit_events` step. No `traffic` / `events` step. No `traces` step.

**Root cause**

Designed in 2026-Q1 (CAB-1411 lineage) for catalog bootstrap. Observability was assumed to be exercised by real prod traffic, not by the seeder.

**Consequence**

After `make seed` on a fresh k3d / staging cluster:

- `audit_events` table = empty → `/audit-log` shows zero entries with `source=null` (no demo banner because demo fallback is `false` in prod and only `dev`/`test` enable it via `config.py:213`).
- Prometheus has zero `stoa_http_requests_total` series for the seeded routes → `/observability/live-calls` KPIs all zero.
- OpenSearch `otel-v1-apm-span-*` empty → Live Traces card empty.

**Effort to close**

| Option | What | Effort |
|---|---|---|
| 1A | New step `audit_events` (direct PG insert via `AuditService`, 50–200 events/tenant over 30d) | ~3h |
| 1B | New step `traffic` (httpx loop hitting gateway with seeded creds → fires audit + Prom + spans naturally) | 1–2 days |

1A unlocks audit log demo without depending on gateway up. 1B unlocks the full stack but couples the seeder to a live gateway.

---

## Gap 2 — `audit_events.tenant_id` is the resource owner, not the caller

**Code**

```text
control-plane-api/src/routers/apis.py        — 3 emit_audit_event sites
control-plane-api/src/routers/tenants.py     — 8 sites
control-plane-api/src/routers/users.py       — 1 site
control-plane-api/src/services/deployment_service.py  — 2 sites
control-plane-api/src/services/promotion_service.py   — 2 sites
```

All call `kafka_service.emit_audit_event(tenant_id=tenant_id, ...)` where `tenant_id` is the **target resource's** tenant — not the **caller's** tenant.

**Evidence**

Per `docs/audits/2026-05-09-audit-log-runtime-verification/findings.md:144`:

- Tenant `demo`: 11 non-chat events (organic) + 35 ingested between PR-1A activation and PR-1A6 trigger.
- Tenant `free-aech` (the logged-in operator's workspace): **2 events** total over 30 days, both `update api/api-beta success` from 2026-04-25.

**Root cause**

The product/RBAC model treats audit_events as "things done **to** my tenant's resources". Cross-tenant operators (`cpi-admin` editing `demo` while logged into `free-aech`) generate events tagged with the **target** tenant. The UI filters `/v1/audit/{tenant_id}` against the active workspace.

**This is not a bug.** It is a product decision that should be re-examined.

**Open question (for challenger)**

Should the audit log expose two views?
- `by_resource` (current): "what was done to my tenant's resources"
- `by_actor`: "what my tenant's users did" (regardless of target)

The `audit_events` schema (alembic `044_create_audit_events.py`) has `actor_id` but no `actor_tenant_id`. Adding the second view requires:
- Migration: new nullable column `actor_tenant_id` + index
- Backfill: derive from `actor_id` via `users` table
- Repo + UI: filter toggle "By resource | By actor"
- ADR-NN to document the model

Effort: ~4h code + ~2h doc + 1d backfill on prod data.

---

## Gap 3 — Trace pipeline: code ready, infra status unverified

**Chain (code-side, fully wired)**

```text
stoa-gateway (OTel SDK) [stoa-gateway/src/telemetry/mod.rs:24]
  ENV STOA_OTEL_ENDPOINT [charts/stoa-platform/values-prod.yaml:57]
  → http://stoa-alloy-otlp.stoa-monitoring:4317
    → Alloy
      → Data Prepper
        → OpenSearch index otel-v1-apm-span-* [services/opensearch_provisioner.py:84]
          ← MonitoringService.list_transactions_from_spans [monitoring_service.py:307]
            ← /v1/monitoring/transactions [routers/monitoring.py:107]
              ← apiService.getTraces → CallFlowDashboard "Live Traces"
```

Fallback: Tempo via `tempo_service.search_traces` (`config.py:411` `TEMPO_INTERNAL_URL`, `routers/monitoring.py:128`). `OPENSEARCH_TRACES_ENABLED=True` by default (`config.py:416`).

**Evidence the pipeline is empty in prod**

- `docs/audits/2026-05-08-live-calls-runtime-verification/findings.md:230`: "Tempo/OpenSearch trace pipeline absence: not a PR-2 concern. The empty state correctly tells the operator where to look."
- UI empty message (`CallFlowDashboard.tsx`): _"No traces yet — ensure gateway routes are configured and the observability pipeline (Alloy, Tempo, OpenSearch) is active"_

**Root cause hypotheses (to confirm on cluster)**

1. Alloy not deployed in `stoa-monitoring` namespace.
2. Alloy deployed but Data-Prepper config not writing `otel-v1-apm-span-*`.
3. Index exists but mapping rejects gateway spans (resource attributes mismatch).

**Effort**

`kubectl -n stoa-monitoring get pods,svc,cm` + `curl https://opensearch.gostoa.dev/_cat/indices/otel-v1-apm-span-*` will localize the gap in 15 minutes. Then 2h to 1d depending on which hypothesis fires.

---

## Gap 4 — Guardrails counters: only fire from MCP path; UI conflates "no series" and "count = 0"

**Code (registry + helpers)**

```text
stoa-gateway/src/metrics.rs:205    GUARDRAILS_PII_DETECTED        (CounterVec)
stoa-gateway/src/metrics.rs:215    GUARDRAILS_INJECTION_BLOCKED   (CounterVec)
stoa-gateway/src/metrics.rs:226    GUARDRAILS_CONTENT_FILTERED    (CounterVec)
stoa-gateway/src/metrics.rs:1054-1073   record_guardrails_{pii,injection,content_filter}
```

**Call sites (the entire emission surface)**

```text
stoa-gateway/src/mcp/handlers.rs:712   record_guardrails_pii("redacted")
stoa-gateway/src/mcp/handlers.rs:719   record_guardrails_content_filter("sensitive", category)
stoa-gateway/src/mcp/handlers.rs:729   record_guardrails_injection(&request.name)
stoa-gateway/src/mcp/handlers.rs:737   record_guardrails_content_filter("blocked", category)
stoa-gateway/src/mcp/handlers.rs:739   record_guardrails_pii("blocked")
```

**All five emit-sites live in `mcp/handlers.rs`.** No emission from `proxy/`, `router/`, or other modes. So:

- Non-MCP traffic (proxy, sidecar shadow, etc.) never increments guardrails counters.
- MCP traffic that does not trip a guard never increments either.
- Result in prod (`docs/audits/2026-05-09-guardrails-runtime-verification/findings.md:75`): `last_sample_at: null` on every guard → 5/5 cards render **"No metrics sample"**.

**Two issues bundled together**

1. **Coverage**: guardrails only instrumented on MCP path. Other modes are silent.
2. **UX semantics**: the AR-1 5-state contract conflates _"counter does not exist"_ with _"counter exists, count = 0"_. Operator reads "No metrics sample" and assumes the system is broken; reality is "no policy trip in the window".

**Effort**

| Sub-gap | Effort |
|---|---|
| 4A — extend guardrail emission to non-MCP proxy paths | 2–3 days (with regression tests per mode) |
| 4B — split UI state: `metrics_unavailable` (no series) vs `no_trips` (count=0) | ~4h backend (`gateway_observability.py`) + ~4h UI + tests |

4B is independent of 4A and reduces operator confusion immediately even if 4A is deferred.

---

## Severity matrix

| # | Gap | Preuve | Impact démo | Blast prod | Action | Owner candidate |
|---|---|---|---|---|---|---|
| 1 | Seeder catalog-only | `dev.py:5-13` | **Élevé** | Nul | Step `audit_events` (3h) puis step `traffic` (1–2j) | platform |
| 2 | `tenant_id` = ressource | `apis.py` x3, `tenants.py` x8, `audit-log-runtime` finding §6 | Moyen | Moyen (trace de "qui a agi" partielle) | ADR + dual-view migration (~1j) | data |
| 3 | Tempo/Alloy pipeline | `live-calls-runtime` §residual, UI empty message | **Élevé** (Live Traces card vide) | **Élevé** (debug prod) | Diag cluster (1–2h) puis fix infra (2h–1j) | sre |
| 4A | Guardrails non-MCP | `mcp/handlers.rs:712-739` only | Faible | Moyen (faux négatifs sécurité hors MCP) | Étendre emission (2–3j) | gateway |
| 4B | UI conflates 0 vs null | `gateway_observability.py:68`, `findings.md §3` | Faible | Faible–Moyen | Split states (1j) | ui+api |

## Recommended sequence (to be challenged)

1. **Gap 3 diag** — 1–2h, no code. Localizes the Live Traces emptiness. Blocking nothing, unblocks possibly the highest-visibility gap.
2. **Gap 1A** — 3h. Step `audit_events`. Demos and staging immediately get rich audit history without depending on traffic.
3. **Gap 4B** — 1d. UI/API split between "metrics unavailable" and "no trips". Removes a class of operator confusion.
4. **Gap 2 ADR** — Half-day doc. Ticket only after ADR review. Code follows.
5. **Gap 1B** (traffic step) — Defer until 1A is in production.
6. **Gap 4A** (guardrails non-MCP) — Separate MEGA. Out of scope for current observability batch.

## Cross-references

- ADR-067 (UAC/MCP/Smoke doctrine) — relevant for Gap 4 because guardrails are conceptually a UAC/contract concern, not just MCP.
- CAB-1411 — original seeder bootstrap (catalog-only by design).
- CAB-1475 — `audit_events` table introduction (alembic 044).
- CAB-1831 — gateway OTel always-compiled-in.
- CAB-1997 — Data Prepper / `otel-v1-apm-span-*` index.
- PR #2730, #2737, #2738, #2740, #2741, #2742, #2743, #2745 — observability data integrity batch.
- Prior audits:
  - `docs/audits/2026-05-08-live-calls-runtime-verification/findings.md`
  - `docs/audits/2026-05-09-audit-log-runtime-verification/findings.md`
  - `docs/audits/2026-05-09-guardrails-runtime-verification/findings.md`

## Open questions (intended for challenger)

1. Is "by_actor" view of audit log a real product need, or is the current "by_resource" model sufficient? If the org runs cross-tenant ops via `cpi-admin`, the answer matters.
2. Is the trace pipeline (Alloy + Data Prepper + OpenSearch) supposed to be live in this prod, or is the design intentionally Prometheus-only until Q3?
3. Is the AR-1 "5-state" contract complete, or does Gap 4B reveal a missing 6th state (`series_absent` vs `count_zero`)?
4. Should `seeder` ever generate observability data, or is it strictly a catalog tool? If yes, where is the line between "fixture" and "synthetic traffic"?
5. Should guardrails be instrumented at the proxy layer (gateway-wide) or remain MCP-specific until each protocol opts in?

## Residual notes

- No Linear ticket created. Per the operator workflow, ticketing happens after challenger validation of this audit and of the resulting plan.
- No code touched.
- Audit limited to code/config inspection. Cluster verification for Gap 3 explicitly deferred.
