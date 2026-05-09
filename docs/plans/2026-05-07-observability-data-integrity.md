---
id: plan-2026-05-07-observability-data-integrity
triggers: []                           # tactical remediation, no Decision Gate trigger
validation_status: validated           # AR-1..AR-6 filled 2026-05-07 — Claude recommendations accepted by product owner
challenge_ref: ""                      # not required (no triggers); add only if upgraded to challenged
---

# Plan — Observability Data Integrity

## Objectif

Restaurer la cohérence et la véracité des trois pages observability (`/observability/live-calls`, `/audit-log`, `/observability/security`) après la consolidation routes faite par codex (PR #2713 + #2715), qui a livré une façade propre devant des composants encore branchés sur des données incohérentes, vides, ou mockées.

**Source audit**: `docs/audits/2026-05-07-observability/AUDIT.md` (28 findings priorisés HIGH/MED/LOW).

## Scope

- **In**: PRs séquencés données-d'abord (PR-0 quick wins, PR-1A/A2/A3/A4/A5/A6/1B audit log compliance, PR-2 live calls scope, PR-3 guardrails runtime, PR-4 nav IA).
- **Out**: pas de réécriture du pipeline OTel/Loki/Tempo/OpenSearch ; pas de migration schema `audit_events` ; pas de PII erasure UI ; pas de cross-tenant aggregation.

## Go / No-Go criteria

- **Go**: arbitrages AR-1..AR-6 ci-dessous remplis, PR-1A investigation accessible (kubeconfig prod OVH).
- **No-Go**: si l'investigation PR-1A révèle que le Kafka audit consumer n'existe pas en prod (réécriture infra requise hors scope).

---

## TL;DR

11 PR/work items, séquencés **données d'abord, polish ensuite**, regroupés en **2 MEGAs + 1 chore PR**. Updated 2026-05-08 after #2724/#2726/#2727/#2730/#2733/#2734 landed and the activation step moved to stoa-infra (#73/#75).

| Order | PR | Type | MEGA | Priority | Blocked by | Status |
|---|---|---|---|---|---|---|
| 1 | PR-0 | Chore (cosmetic + 1 functional) | None | P0 | — | ✅ #2717 |
| 2 | PR-1A | Investigation (no code) | MEGA-A | P0 | PR-0 merged | ✅ #2721 |
| 3 | PR-1A2 | Consumer restore scope | MEGA-A | P0 | PR-1A complete | ✅ #2723 (Case C) |
| 4 | PR-1A3 | Audit ingestion contract mini-spec (docs) | MEGA-A | P0 | PR-1A2 complete | ✅ #2724 (validated) |
| 5 | PR-1A4 | Audit consumer implementation | MEGA-A | P0 | PR-1A3 merged | ✅ #2726 + corrective #2730 + test fix #2734; post-fix image deployed |
| 6 | PR-1A5 | Verification evidence | MEGA-A | P0 | PR-1A4 deployed | ✅ #2733 (data-path PASS while enabled; disabled at end of test window) |
| 7 | PR-1A6 | Activation A1b + post-activation evidence amend | MEGA-A | P0 | PR-1A5 reviewed + operator go | ⏳ stoa-infra #75 merged/activated; post-activation evidence amend pending |
| 8 | PR-1B | Audit Log API + UI | MEGA-A | P0 | PR-1A6 PASS | blocked — post-activation evidence amend required |
| 9 | PR-2 | Live Calls metric integrity | MEGA-B | P0 | PR-0 merged | ✅ #2727 merged |
| 10 | PR-3 | Security & Guardrails runtime truth | MEGA-B | P1 | PR-3A runtime-truth contract merged | blocked — contract drafted in `docs/plans/2026-05-10-guardrails-runtime-truth-contract.md` |
| 11 | PR-4 | Navigation IA cleanup | MEGA-B | P2 | PR-3 merged | blocked |

**Total estimated**: ~62 pts (MEGA-A grew to ~32pt/7 phases, MEGA-B 21pt/3 phases, PR-0 1pt).

---

## Assumptions

- L'audit `docs/audits/2026-05-07-observability/AUDIT.md` reflète l'état prod 2026-05-07 (tenant `free-aech`, CPI Admin role).
- Les PRs codex #2713 + #2715 ont bien été déployés (`control-plane-ui` ≥ 1.7.3).
- Accès kubectl read-only OVH prod disponible pour PR-1A (ou délégation à un SRE).
- L'équipe gateway Rust est joignable si PR-2 conclut à un fix Rust (peu probable — voir section PR-2 step 0).

## Arbitrages requis (à remplir avant exécution)

Ces décisions doivent être tranchées par le product owner **avant que codex démarre les PRs concernés**. Codex ne doit pas trancher implicitement. Pour valider, remplacer `STATUS: pending` par `STATUS: <decision>` + date dans la colonne **Décision** de chaque ligne. Une fois les 6 remplis, passer le frontmatter `validation_status` de `draft` à `validated`.

| # | Décision à prendre | Bloque | Recommandation Claude | Décision |
|---|---|---|---|---|
| **AR-1** | Security Posture (Governance) ↔ Security & Guardrails (Observability): fusion ou clarification IA stricte ? | PR-3, PR-4 | **Clarifier** — Posture = état/findings/score statique ; Guardrails = events runtime. Documenter sous-titres. Pas de fusion (personas distincts: compliance officer vs SRE). | **STATUS: validated 2026-05-07** — Clarifier (no fusion). Sous-titres distincts: Security Posture = "Compliance findings, security score, configuration assessment" ; Security & Guardrails = "Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring". |
| **AR-2** | "Rate Limit" appartient à `/observability/security` ou `/observability/live-calls` ? | PR-3 | **Garder dans Security** (protection, pas signal de trafic). Corriger filter (S6) au lieu de retirer la carte. | **STATUS: validated 2026-05-07** — Garder Rate Limit dans Security & Guardrails. S6 filter no-op corrigé en PR-0 (#2717 merged). PR-3 rendra la carte cliquable avec un vrai filtre `rate-limit` ou la gardera non-cliquable selon données disponibles. |
| **AR-3** | Demo data fallback côté audit API (`routers/audit.py:259 _init_demo_data()`): garder ou supprimer en prod ? | PR-1B | **Supprimer en prod**, garder en dev/test via env var `STOA_AUDIT_DEMO_FALLBACK=false` par défaut. | **STATUS: validated 2026-05-07** — Demo fallback OFF en prod. Env var `STOA_AUDIT_DEMO_FALLBACK=false` par défaut, `true` en dev/test. Quand le fallback déclenche (env=true ET PG+OS indisponibles), réponse contient `{"source": "demo", "warning": "Audit backend unavailable"}` — jamais silencieux. |
| **AR-4** | Auto-refresh policy audit log: garder 30s polling fixe ou exponential backoff sur erreur ? | PR-1B | **Backoff exponentiel sur erreur** (30s → 60s → 120s → 300s plafonné), reset au prochain succès. Pas de refactor SWR (over-engineering). | **STATUS: validated 2026-05-07** — Backoff exponentiel: 30s → 60s → 120s → 240s → 300s plafonné sur erreurs consécutives. Reset à 30s au prochain succès. Pas de SWR/TanStack refactor. |
| **AR-5** | Route label semantics for Live Calls: how to group route-level metrics ? | PR-2 | Initial recommendation was `'(unlabelled)'` fallback. **PR-2 step 0 evidence (#2720) refines**: `http_route` is present on 306/306 current series, `path` on 0/306. Use `http_route` as canonical route label. Keep `'(unlabelled)'` only as fallback when the expected label is missing or empty. | **STATUS: validated 2026-05-08** — Use `http_route` as canonical route label for Live Calls. Replace `path` groupings everywhere in `CallFlowDashboard.tsx`. `usePrometheus.ts:161` fallback renamed `'unknown'` → `'(unlabelled)'` (also covers empty string). Filter `(unlabelled)` from Top Routes/Heatmap when ≥1 valid `http_route` exists ; render explicit EmptyState "Route labels unavailable" when 100% are unlabelled. |
| **AR-6** | Heatmap synthétique `CallFlowDashboard.tsx:336-361`: supprimer ou réécrire en vraie query ? | PR-2 | **Supprimer** (cacher derrière `<EmptyState>` "Heatmap unavailable"). Réécriture vraie = ticket séparé non-bloquant. | **STATUS: validated 2026-05-08** — Remove synthetic heatmap (hash + flatMap business-hours distribution). EmptyState "Traffic heatmap unavailable. A real range-query heatmap is not wired yet for the selected time range." Real `query_range` heatmap grouped by `http_route` deferred to a separate non-blocking follow-up ticket created after PR-2 merge. |

**Note**: l'arbitrage est inline dans ce plan (pas un fichier séparé). Un nouveau commit met à jour `STATUS: <decision>` + flip `validation_status: validated` quand les 6 sont remplis. Codex lit ce frontmatter au début de chaque PR.

---

## Investigation results — 2026-05-08

### PR-1A — Audit ingestion (#2721 merged)

Evidence: `docs/audits/2026-05-08-audit-ingestion/findings.md`

**Verdict: BLOCKED_FOR_PR-1B_SCOPING.**

OVH prod has Kafka topics `stoa.audit.trail` and `audit-log`, but **no consumer group is subscribed** to either. PostgreSQL `audit_events` exists with 113 562 rows, but newest event is `2026-05-03 20:04:46+00` and `0` rows in the last 24h. Source scan reveals two parallel sinks: direct `AuditService.record_event(...)` writes (chat paths, confirmed historical) and Kafka-only `kafka_service.emit_audit_event(...)` (deployment, promotion, apis, tenants, users — all CONFIRMED_UNCONSUMED).

**Impact**: PR-1B is **blocked**. Do not implement Audit Log `/stats`, `/actions`, actor resolution, demo fallback toggle, or refresh backoff until audit ingestion is restored and at least one non-chat event is visible through `/v1/audit/{tenant_id}`.

**Next**: PR-1A2 inserted (consumer restore/scope) — see verdict below.

This was the explicit **No-Go condition** in the plan's Go/No-Go criteria. The plan is not abandoned — only PR-1B is gated; everything else proceeds.

### PR-1A2 — Audit consumer restore scope (#2723 merged)

Evidence: `docs/audits/2026-05-08-audit-consumer-restore/scoping.md`

**Verdict: CONSUMER_IMPLEMENTATION_NOT_FOUND** (Case C from the PR-1A2 codex prompt).

The repository has Kafka audit **producers** (`emit_audit_event(...)` to `Topics.AUDIT_LOG = "stoa.audit.trail"`) and 5 generic Kafka consumer patterns (`deployment_consumer`, `promotion_deploy_consumer`, `chat_metering_consumer`, `billing_metering_consumer`, `error_snapshot_consumer`), but **no consumer that persists `stoa.audit.trail`, `audit-log`, or `stoa.audit.events` into PostgreSQL `audit_events`**. No `ENABLE_AUDIT_CONSUMER` flag, no audit consumer startup task, no audit consumer manifest.

**Topic Contract Drift identified** (3 audit-topic names in circulation):

| Name | Evidence | Status |
|---|---|---|
| `stoa.audit.trail` | `Topics.AUDIT_LOG`, active `emit_audit_event(...)` producer | **Active producer** |
| `audit-log` | Prod Redpanda topic from PR-1A evidence | Runtime topic exists, no repo producer/consumer |
| `stoa.audit.events` | `Topics.AUDIT_EVENTS` constant + runbooks | Documented/legacy, no repo consumer |

This is a **contract ambiguity** that PR-1A3 must trancher avant que PR-1A4 implémente.

**Impact**: building a consumer is **new ingestion architecture**, not a restore. PR-1A2 stayed docs-only as designed (Case C). After the PR-1A4 activation incident, MEGA-A grew to **7 phases**:

```
Phase 1 — PR-1A   Investigation (#2721 ✅)
Phase 2 — PR-1A2  Consumer restore scope (#2723 ✅, Case C)
Phase 3 — PR-1A3  Audit ingestion contract mini-spec (docs-only) — #2724 ✅ validated
Phase 4 — PR-1A4  Audit consumer implementation (backend + manifest) — #2726 ✅ + #2730/#2734 corrective
Phase 5 — PR-1A5  Verification evidence — #2733 ✅ data-path PASS while enabled, caveat disabled after test
Phase 6 — PR-1A6  Activation A1b + post-activation evidence amend — stoa-infra #75 merged, evidence amend pending
Phase 7 — PR-1B   Audit Log API + UI (gated on PR-1A6 PASS)
```

**PR-1B unblock signal** (canonical, ne pas dévier): at least one **non-chat** audit row appears in `/v1/audit/{tenant_id}` after a manual API mutation (e.g. tenant create or API create) **while the consumer is continuously enabled**. PR-1A5 proved the data path while enabled; PR-1A6 must amend the evidence after activation.

### PR-2 step 0 — Live Calls PromQL evidence (#2720 merged)

Evidence: `docs/audits/2026-05-08-live-calls-investigation/promql-evidence.md`

**Verdict: READY_FOR_PR-2_CODE_SCOPING.**

Current `stoa_http_requests_total` exposes `http_route` on **306/306** series, `path` on **0/306**. Histogram series `stoa_http_request_duration_seconds_bucket` follow the same pattern (`http_route` 3627/3627, `path` 0/3627). The 24h `path` evidence shown earlier (88 entries) is **historical/legacy** stale series, not current data.

**Impact**: the audit finding L2 ("path=unknown") was misdiagnosed. The cause is **the dashboard groups by the wrong label** (`path`), not a gateway emission bug. The `'unknown'` displayed comes from `usePrometheus.ts:161` fabricating a fallback when the queried label is absent.

**Next**: PR-2 codex prompt updated below to use `http_route` as the canonical label everywhere. No gateway-side investigation required; `path` is simply not a current label on these metrics. Note for Top Routes histogram: confirm via the same evidence pack that `http_route` is exposed on the histogram metric (it is — 3627/3627).

### PR-1A4 — Incident 2026-05-07: implementation merge with unsafe default

Factual timeline:

- 2026-05-07 18:39 UTC: #2726 merged with code default `ENABLE_AUDIT_TRAIL_CONSUMER` fallback `"true"` and `control-plane-api/k8s/deployment.yaml` env value `"true"`.
- 18:49 UTC: stoa-infra image tag auto-bumped to the #2726 build by `github-actions[bot]` (~10 min after merge).
- 18:50:36 UTC: ArgoCD sync rolled cp-api pods; consumer started in prod with no explicit chart-level gate.
- 19:08 UTC: #2730 corrective merged (Python default `"true"` -> `"false"`, base manifest `"false"`, regression test added).
- 19:23 UTC: stoa-infra #73 merged (chart values explicit `ENABLE_AUDIT_TRAIL_CONSUMER: "false"`).
- 19:24:38 UTC: 1 audit event ingested (action=`export`, tenant=`demo`, id=`b9ca45fb-67b3-4823-98af-c198c3d68871`); schema valid, PII masking applied, `_kafka` metadata present. Volume = 1 row; no corruption.
- 19:38 UTC: ArgoCD hard-refresh + auto-sync; pods rolling-restart with env override active; consumer effectively OFF.
- 2026-05-08 06:18 UTC: #2730 main build hung 6h+ on `Run tests` (root cause: regression test used `importlib.reload(main)` which broke conftest patches; subsequent lifespan test attempted real Kafka connect, hung the runner). #2734 replaced the reload-based test with a static regex check; #2734 merged 06:30 UTC; main build succeeded; auto-bump fired ~07:00 UTC; ArgoCD synced; pods ran image post-fix `dev-1803ef125...` with double safety (code default `"false"` AND chart override `"false"`).

Runbook violation: A1a was supposed to deploy disabled first, but auto-bump + auto-sync activated the consumer before the chart gate landed. Volume was contained (one verified row, no corruption), but this is process-correctable for future Kafka/PG-touching PRs.

### Process notes — Kafka/PG PR safety gate

Kafka/PG/data-path PRs require explicit operator go after reviewer flags risk, not just a review APPROVE.
The #2726 -> #2730 -> #2734 sequence is the canonical case study.
Safe rollout means code can merge with fail-closed defaults, but activation must be a separately controlled runtime step.
If auto-bump + ArgoCD can activate the path, the chart gate must land before the code image can roll.

## Activation A1b — staged rollout (stoa-infra #75 merged; post-activation evidence pending)

Status note: the context that opened this plan-update still treated stoa-infra #75 as DRAFT/HOLD. GitHub verification on 2026-05-08 shows stoa-infra #75 was merged at 2026-05-08 07:40:34 UTC, and a read-only OVH prod check showed `ENABLE_AUDIT_TRAIL_CONSUMER="true"` on `stoa-control-plane-api` revision 517 with `audit-trail-pg-consumer` `STATE=Stable`, `MEMBERS=1`, `TOTAL-LAG=0`. This does **not** unblock PR-1B until the post-activation evidence amend is recorded.

- Single change: `charts/control-plane-api/values.yaml` flips `ENABLE_AUDIT_TRAIL_CONSUMER` from `"false"` to `"true"`.
- stoa-infra #75 was opened in **draft** explicitly; merge required explicit operator go.
- Post-merge runbook is in the stoa-infra #75 PR body; do not duplicate it here.
- Rollback path: open a follow-up PR flipping back to `"false"` and re-sync ArgoCD. Kafka retention 7 days mitigates short OFF windows.
- Defense-in-depth: after activation, the consumer starts only if master gate `STOA_ENABLE_KAFKA_CONSUMERS` is effectively true in prod and chart override `=true`. The cp-api code default is `"false"` (#2730), which is a fail-closed last line of defense if the chart gate is removed.
- After activation, evidence file `docs/audits/2026-05-09-audit-consumer-verification/findings.md` must be amended (or a follow-up file opened) with a verdict line like: `**VERDICT: PR-1B_UNBLOCKED — continuous ingestion verified <UTC timestamp>.**`

---

## Specs policy

Ce plan **ne crée pas** de spec produit complète: le travail est une remédiation tactique post-audit, pas une nouvelle feature. Le triptyque suffisant est: **(1) audit factuel** (`docs/audits/2026-05-07-observability/AUDIT.md`) + **(2) plan canonique** (ce document) + **(3) prompts codex avec acceptance criteria + tests** (sections PR ci-dessous).

Codex peut implémenter directement à partir de ce plan pour les PRs où la surface API/UI est bornée. **Mini-specs contractuelles requises** uniquement quand codex risque d'inventer la forme de réponse ou de masquer des sémantiques `null/0/disabled/stale/error` mal distinguées. Voir tableau:

| PR | Mini-spec required ? | Reason |
|---|---|---|
| PR-0 | No | Bounded hygiene changes, file:line edits enumerated. |
| PR-1A | No | Investigation-only, evidence pack format défini par checklist. |
| PR-1B | **Yes** | New API endpoints + actor resolution + demo fallback semantics. Voir Annex A. |
| PR-2 | Partial | PromQL evidence pack (PR-2 step 0) + data integrity rules dans le prompt. Pas de nouveau endpoint. |
| PR-3 | **Yes** | New `/guardrails/config` endpoint + null/zero/stale/disabled/error semantics. Voir Annex B + `docs/plans/2026-05-10-guardrails-runtime-truth-contract.md`. |
| PR-4 | Partial | Wording IA dépend de AR-1; pas de nouvelle surface API. |

Une mini-spec doit fixer: shape request/response, sémantique d'état (null vs 0 vs disabled vs stale vs error), fallback behavior, acceptance criteria, tests obligatoires. Pas plus.

---

## MEGA-A — Audit Log Data Integrity

**Goal**: Garantir que `/audit-log` reflète la couverture DORA/NIS2 attendue (toutes les actions, pas seulement chat) et que l'UI ne ment pas sur l'état des données.

**Estimated**: ~32 pts (7 phases)

**Binary DoD**:
- [ ] Production audit log retourne au moins une entrée non-`chat_*` après exercice manuel d'un emit path (ex: création API) **while the consumer is continuously enabled after A1b activation**.
- [ ] Date filters fonctionnels (mapping UI→API correct).
- [ ] KPIs (Total/Successful/Failed/Unique Actors) reflètent la fenêtre filtrée, pas la page courante.
- [ ] Demo data désactivé en prod (sauf override env explicite).
- [ ] Tests régressifs: mapping date filters + actor resolution + stats endpoint.

---

## MEGA-B — Runtime Observability Data Integrity

**Goal**: Garantir que `/observability/live-calls` et `/observability/security` ne présentent jamais des données incohérentes (KPI vs breakdown), absentes mais affichées comme zéro, ou synthétiques.

**Estimated**: 25 pts (3 phases)

**Binary DoD**:
- [ ] Live Calls: aucune contradiction KPI vs breakdown sans bannière "scope mismatch".
- [ ] `path="unknown"` (ou variante) traité explicitement, pas affiché comme route normale.
- [ ] Pas de heatmap synthétique en prod.
- [ ] Guardrails: chaque carte distingue `disabled`, `enabled+0`, `stale`, `error`.
- [ ] Time range selector cohérent entre Live Calls et Guardrails.
- [ ] Sidebar: pas de lien vers route legacy redirigée (`/gateway-security`, `/gateway-guardrails`).

---

# PR-0 — Quick Wins (Cosmetic + A4 functional)

**Branch**: `chore/observability-quick-wins`
**MEGA**: None (standalone chore)
**Estimated**: 1 pt, ~50 LOC, 30 min
**Risk**: Low

## Goal

Remove cosmetic noise and fix the broken date filter mapping before data PRs start. Allows reviewers of PR-1B and PR-2 to focus on substance, not stale titles.

## Findings addressed

L7, S1, S6, S7 (cosmetic), A4 (functional bug).

## In scope

| Fix | File | Change |
|---|---|---|
| L7 | `control-plane-ui/src/pages/CallFlow/CallFlowDashboard.tsx:440` | `<h1>Call Flow</h1>` → `<h1>Live Calls</h1>` |
| S1 | `control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.tsx:191` | `<h1>Gateway Guardrails</h1>` → `<h1>Security & Guardrails</h1>` |
| S6 | `GuardrailsDashboard.tsx:175-182` | Rate Limit card: retirer `filter: 'all'` → soit `filter: 'rate-limit'` (avec mapping ajouté), soit faire la carte non-clickable (`onClick` retiré + cursor par défaut) |
| S7 | `GuardrailsDashboard.tsx:276` | `navigate(\`/call-flow/trace/${event.trace_id}\`)` → `navigate(\`/observability/live-calls/trace/${event.trace_id}\`)` |
| A4 | `control-plane-ui/src/pages/AuditLog.tsx:127-128` | `params.date_from = filters.start_date` → `params.start_date = filters.start_date` (idem `date_to` → `end_date`) |

## Out of scope

- Pas de modification logique (KPIs, queries Prometheus, endpoints API).
- Pas de retrait des entrées sidebar legacy (reporté à PR-4 après arbitrage AR-1).
- Pas de timestamp "last successful refresh" (reporté à PR-1B avec backoff).

## Codex prompt

```
You are working on the STOA Console UI repository (control-plane-ui).
This PR is a hygiene-only PR called "Observability Quick Wins". It must NOT touch business logic, Prometheus queries, or API contracts. It is a preflight cleanup before larger data-integrity PRs (MEGA-A and MEGA-B in Linear).

Apply exactly these 5 changes:

1. control-plane-ui/src/pages/CallFlow/CallFlowDashboard.tsx
   - Line 440: change <h1>Call Flow</h1> to <h1>Live Calls</h1>
   - Update the subtitle on line 441-443 from "Real-time request flow across deployment modes — Gateway, Link, Connect" to match the breadcrumb terminology: "Recent calls, trace IDs, latency, and request flow across Gateway, Link, and Connect"
   (NOTE: the second subtitle is already what the rendered page shows in production; the first one is dead code overridden by a parent layout. Verify which one wins by running the dev server before deciding.)

2. control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.tsx
   - Line 191: change <h1>Gateway Guardrails</h1> to <h1>Security & Guardrails</h1>
   - Line 194: align subtitle if needed.

3. control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.tsx
   - Lines 175-182 (Rate Limit card definition): change `filter: 'all'` to `filter: 'rate-limit'`
   - Add `'rate-limit'` to the FilterType union (line 37) and to ACTION_TO_FILTER (line 39-45) mapping the action 'rate-limited' (or whatever string the events table emits) to 'rate-limit'.
   - Add 'rate-limit' to FILTER_LABELS (line 47-53) with label "Rate Limit".
   - If the events table does not currently emit a rate-limit action, leave the card clickable but make activating the filter show "No rate-limit events" (do NOT silently filter to nothing).

4. control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.tsx
   - Line 276: change navigate(`/call-flow/trace/${event.trace_id}`) to navigate(`/observability/live-calls/trace/${event.trace_id}`)

5. control-plane-ui/src/pages/AuditLog.tsx
   - Lines 127-128: change
     if (filters.start_date) params.date_from = filters.start_date;
     if (filters.end_date) params.date_to = filters.end_date;
     to
     if (filters.start_date) params.start_date = filters.start_date;
     if (filters.end_date) params.end_date = filters.end_date;
   - Lines 173-178 (handleExport): same rename for the export query.

Acceptance:
- Run `npm run test -- --run src/pages/CallFlow/ src/pages/GatewayGuardrails/ src/pages/AuditLog.test.tsx`. Tests must pass.
- Run `npm run lint`. No new warnings.
- Add a regression test in src/pages/AuditLog.test.tsx asserting that loadData calls apiService.get with `params.start_date` (not `date_from`) when the user sets a date filter. Use the existing test infrastructure (helpers.tsx, MSW or direct apiService mock).
- Add a regression test in src/__tests__/regression/observability-titles.test.ts asserting that for routes /observability/live-calls and /observability/security, the rendered <h1> matches the last breadcrumb label.

Out of scope:
- Do NOT modify Prometheus queries.
- Do NOT modify the API client beyond the param renames.
- Do NOT touch sidebar nav entries (deferred to PR-4).
- Do NOT add the "last successful refresh" timestamp (deferred to PR-1B).
- Do NOT remove the heatmap (deferred to PR-2).

Commit message: chore(ui): observability quick wins — titles, rate-limit filter, audit date params

Open as PR with body referencing docs/audits/2026-05-07-observability/AUDIT.md findings L7, S1, S6, S7, A4.
```

## Acceptance criteria (binary)

- [ ] `<h1>` matches breadcrumb on `/observability/live-calls` and `/observability/security` (verified via Playwright in dev server).
- [ ] Date filter on `/audit-log` actually changes returned results (manual test).
- [ ] Rate Limit card click on `/observability/security` either filters to rate-limit events or shows explicit "No rate-limit events".
- [ ] Click on a guardrail event navigates to `/observability/live-calls/trace/...` (no transient redirect from `/call-flow/trace/...`).
- [ ] Tests added: `AuditLog.test.tsx` (param naming), `observability-titles.test.ts` (h1 ↔ breadcrumb).

## Tests required from Codex

1. `AuditLog.test.tsx` regression: filter date_from → API param `start_date`.
2. `observability-titles.test.ts` regression: h1 = last breadcrumb label.
3. `GuardrailsDashboard.test.tsx` regression: clicking Rate Limit card sets filter, doesn't trigger no-op.

## Files probably touched

- `control-plane-ui/src/pages/CallFlow/CallFlowDashboard.tsx`
- `control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.tsx`
- `control-plane-ui/src/pages/AuditLog.tsx`
- `control-plane-ui/src/pages/AuditLog.test.tsx`
- `control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.test.tsx`
- `control-plane-ui/src/__tests__/regression/observability-titles.test.ts` (new)

---

# PR-1A — Audit Ingestion Investigation (no code)

**Branch**: `investigate/audit-ingestion-coverage`
**MEGA**: A — Phase 1
**Estimated**: 3 pts, 0 LOC (evidence pack)
**Risk**: requires prod read-only access

## Goal

Determine **why** the production `audit_events` PostgreSQL table for tenant `free-aech` contains only chat-related events, and produce an evidence pack that defines the scope of PR-1B.

## Findings addressed

A1 (compliance scope), partial A8 (cross-tenant visibility).

## Hypotheses to test

1. **H1**: Kafka consumer `audit-events → audit_events PG` is down or not deployed.
2. **H2**: `kafka_service.emit_audit_event()` is called by chat code paths but **wraps a try/except that swallows errors** for non-chat paths.
3. **H3**: cp-api emits to Kafka but the Kafka topic exists only in some environments (e.g. demo cluster only).
4. **H4**: Multiple cp-api deployments emit to different sinks (PG vs OpenSearch vs nothing).
5. **H5**: The `audit_events` PG table has a tenant_id filter that excludes most events (RLS policy gone wrong).

## Investigation tasks

```bash
# Run from a session with prod kubeconfig (~/.kube/config-ovh)

# T1: list audit events by event class in prod, last 30 days
kubectl exec -n stoa-system deploy/control-plane-api -- python3 - <<'EOF'
import asyncio, asyncpg, os
async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch("""
      SELECT action, COUNT(*) AS n
      FROM audit_events
      WHERE timestamp > NOW() - INTERVAL '30 days'
      GROUP BY action
      ORDER BY n DESC
    """)
    for r in rows: print(r)
asyncio.run(main())
EOF

# T2: check Kafka consumer lag for audit-events topic
kubectl -n kafka exec deploy/kafka-client -- \
  kafka-consumer-groups.sh --bootstrap-server kafka-bootstrap:9092 \
  --group audit-events-consumer --describe

# T3: tail cp-api logs for audit emit failures
kubectl -n stoa-system logs deploy/control-plane-api --since=24h | \
  grep -iE 'audit|emit_audit' | head -50

# T4: check that emit_audit_event is awaited everywhere (not fire-and-forget)
grep -rn 'kafka_service.emit_audit_event' control-plane-api/src/ | \
  while read line; do
    file=$(echo "$line" | cut -d: -f1)
    lineno=$(echo "$line" | cut -d: -f2)
    awaited=$(sed -n "$((lineno-1))p;${lineno}p" "$file" | grep -c 'await')
    echo "[awaited=$awaited] $line"
  done

# T5: verify the demo fallback is not active in prod
kubectl exec deploy/control-plane-api -- env | grep -iE 'audit|demo'
```

## Codex prompt

```
You are an SRE running a read-only investigation on production STOA platform.

Goal: produce an evidence pack at docs/audits/2026-05-08-audit-ingestion/findings.md that explains why the /audit-log page on console.gostoa.dev shows only chat-related events for tenant free-aech, despite 20+ audit emit sites across the cp-api codebase.

Required sections in findings.md:
1. Inventory of audit emit sites (grep `emit_audit_event` across control-plane-api/src/).
   For each site: file:line, action emitted, whether the call is awaited or fire-and-forget, and whether it sits inside a try/except that could swallow errors.

2. Production state of `audit_events` PG table:
   - Total row count last 30 days.
   - Distinct `action` values + count per action.
   - Distinct `tenant_id` values + count per tenant.

3. Production state of Kafka topic `audit-events`:
   - Topic exists? (yes/no)
   - Consumer group `audit-events-consumer` lag.
   - Last successful commit timestamp.

4. Per-emitter status: for each of the 20+ emit sites, mark CONFIRMED-WORKING / CONFIRMED-BROKEN / UNKNOWN with evidence.

5. Recommended scope for PR-1B:
   - List of emit sites that need a fix.
   - List of API contract changes needed (e.g. add `/v1/audit/{tenant_id}/stats`).
   - Risk: schema migration on `audit_events` if `user_email` is missing for historical rows.

DO NOT write any production code or modify any service. DO NOT delete or migrate audit data.
DO use kubectl exec --readonly via the cp-api pod (the `-i` flag is required to pipe Python heredocs — see memory note `reference_ovh_prod_sql_via_cp_api_pod.md`).
DO archive the raw kubectl outputs in docs/audits/2026-05-08-audit-ingestion/raw/.

Deliverable: a single markdown file. No code changes. PR description: "Investigation only — no code changes. Evidence pack for MEGA-A PR-1B scoping."
```

## Out of scope

- Pas de modification de code (PR-1A est strictement read-only).
- Pas de migration de données.
- Pas de fix immédiat même si trivial — note dans findings, fix dans PR-1B.

## Acceptance criteria (binary)

- [ ] `findings.md` contient les 5 sections.
- [ ] Au moins 5 emit sites classés CONFIRMED-WORKING/BROKEN/UNKNOWN avec evidence.
- [ ] Kafka topic + consumer status documenté.
- [ ] Un scope explicite pour PR-1B est dérivé.

## Files probably touched

- `docs/audits/2026-05-08-audit-ingestion/findings.md` (new)
- `docs/audits/2026-05-08-audit-ingestion/raw/*.txt` (new)
- 0 source files modified.

## Risk + dependencies

- Requires kubeconfig OVH prod read-only.
- Doit s'exécuter pendant les heures bureau (au cas où l'investigation déclenche une alerte).
- Bloque PR-1B (PR-1B ne peut pas démarrer sans le findings).

---

# PR-1B — Audit Log API + UI

> ⛔ **BLOCKED — 2026-05-08, status updated after PR-1A4 incident + A1b activation.** Gating chain: ✅ PR-1A3 (#2724 merged, validated) → ✅ PR-1A4 (#2726 merged + corrective #2730/#2734) → ✅ PR-1A5 (#2733 data-path PASS while enabled, caveat: disabled after test) → ✅ stoa-infra #75 activation merged 2026-05-08 07:40 UTC → ⏳ post-activation evidence amend showing continuous ingestion. **PR-1B starts only after the remaining ⏳ item demonstrates that at least one non-chat audit row is visible via `/v1/audit/{tenant_id}` after a manual API mutation in production while the consumer is continuously enabled**. No exception, no early start "in parallel".

**Branch**: `feat/audit-log-coverage-and-ui`
**MEGA**: A — Phase 7 (was Phase 3; PR-1A3/PR-1A4/PR-1A5/PR-1A6 inserted)
**Estimated**: 13 pts, ~400 LOC (backend + frontend + tests)
**Risk**: depends on PR-1A5 evidence

## Goal

Restaurer la couverture audit promise (compliance DORA/NIS2), exposer des stats globales, résoudre les actor IDs en email/displayName, et nettoyer le state stale/error UX.

## Findings addressed

A1, A2, A3, A5, A6 (reformulé), A7, A8, A9.

## In scope

### Backend (`control-plane-api/`)

1. **Fix audit emitters identified by PR-1A** (probable: ajout `await`, gestion d'erreurs, vérification que tous les sites passent par `kafka_service.emit_audit_event`).
2. Nouveau endpoint `GET /v1/audit/{tenant_id}/stats?start_date=&end_date=&action=&status=`:
   ```python
   class AuditStatsResponse(BaseModel):
       total_events: int
       success_count: int
       failed_count: int
       unique_actors: int
       by_action: dict[str, int]   # top 20
       by_status: dict[str, int]
       window_start: datetime
       window_end: datetime
   ```
3. Nouveau endpoint `GET /v1/audit/{tenant_id}/actions` retournant les actions distinctes vues sur les 30 derniers jours pour ce tenant (cap 100 max).
4. **Désactiver** `_init_demo_data()` en prod (env var `STOA_AUDIT_DEMO_FALLBACK=false` par défaut, override dev/test). Conditionner `audit.py:259` sur cet env var (cf. AR-3).
5. Joindre Keycloak côté API pour résoudre `user_id` → `user_email`/`user_display_name` quand stocké null. Cache 5min via `cachetools.TTLCache` (Keycloak admin API rate-limited).

### Frontend (`control-plane-ui/`)

1. UI consomme `/stats` au lieu de calculer KPIs sur la page courante (cf. A3).
2. UI consomme `/actions` pour populer le filter dynamiquement (cf. A7).
3. Actor display: prefer `user_email || user_display_name || user_id (with badge "unresolved")` (cf. A2).
4. Last-successful-refresh timestamp (cf. A6 reformulé): afficher "Last refreshed: 2026-05-08 14:32:15" + "Refresh failed (retrying in 60s)" en cas d'erreur récente.
5. Auto-refresh exponential backoff (cf. AR-4): 30s → 60s → 120s → 300s plafonné, reset au prochain succès.
6. Split-button Export: CSV / JSON (cf. A5).
7. Locale de `formatTimestamp` (cf. A9): suivre l'i18n du sélecteur EN/FR de la console (`useTranslation()` ou equivalent), pas hard-coded `fr-FR`.

## Out of scope

- Pas de migration de schema `audit_events` (si user_email manque, on résout via Keycloak join, pas via backfill).
- Pas de PII erasure UI (existant côté API mais pas demandé ici).
- Pas de cross-tenant view pour cpi-admin (A8) — ticket séparé futur.

## Codex prompt

```
You are working on STOA control-plane-api (Python 3.11, FastAPI, SQLAlchemy 2.0 async) and control-plane-ui (React 18, TS, Vite).

Context: PR-1A produced an evidence pack at docs/audits/2026-05-08-audit-ingestion/findings.md identifying broken audit ingestion paths. Read it before starting. Findings reference docs/audits/2026-05-07-observability/AUDIT.md sections A1-A9.

This PR fixes the broken emit paths AND adds new UI/API surface for stats + actor resolution + UX state.

Backend tasks:

1. Fix audit emit paths flagged in findings.md.
   - Ensure every emit_audit_event call is awaited.
   - Ensure no try/except swallows audit errors silently. Log at WARN with action+resource_type, but DO NOT raise (audit failure must not break the user-facing operation).
   - Add a regression test per fixed call site: e.g. tests/test_regression_cab_XXXX_audit_apis_create.py

2. Add GET /v1/audit/{tenant_id}/stats:
   - Pydantic AuditStatsResponse: total_events, success_count, failed_count, unique_actors, by_action (top 20), by_status, window_start, window_end.
   - Reuse AuditService query path (PG primary, OpenSearch fallback).
   - Filters: start_date, end_date (note: NAMING MUST BE start_date/end_date — UI uses these, NOT date_from/date_to), action, status.
   - Tests: tests/test_audit_router.py — at least one test per filter, one test for empty result.

3. Add GET /v1/audit/{tenant_id}/actions:
   - Returns {actions: [{action: "api.create", count: 42}, ...]}, top 100 distinct actions in last 30 days.
   - Tests: at least one test verifying the cap and ordering.

4. Add env var STOA_AUDIT_DEMO_FALLBACK (default false in production, true in dev/test).
   Modify audit.py to skip _init_demo_data() when STOA_AUDIT_DEMO_FALLBACK=false.
   When the fallback IS triggered, the response must include {"source": "demo", "warning": "Audit backend unavailable"} — never silent.

5. Add Keycloak-backed actor resolution helper in src/services/audit_service.py:
   async def resolve_actor(user_id: str | None, user_email: str | None) -> ResolvedActor:
       returns {user_id, user_email, user_display_name, resolved: bool}
   - Cache via cachetools.TTLCache(maxsize=2000, ttl=300).
   - When resolution fails (Keycloak down, user not found), return resolved=False but don't raise.
   - Apply this in _pg_event_to_entry and the OpenSearch fallback path.

Frontend tasks (control-plane-ui/src/pages/AuditLog.tsx):

1. Replace local KPI calculation with /stats endpoint.
   - Add a useEffect that fetches /v1/audit/{tenantId}/stats with the same filters as the list query.
   - Display stats in the existing 4 StatCards (Total Events, Successful, Failed, Unique Actors).
   - Update subtitle from "On this page" to the explicit window: e.g. "Last 30 days" or "2026-05-01 → 2026-05-08".

2. Replace hardcoded action filter options with /actions response.
   - On mount, fetch /v1/audit/{tenantId}/actions.
   - Populate the action <select> with the returned list (sorted by count desc).
   - Keep "All actions" as the first option.

3. Actor display refinement:
   - Show user_email when present.
   - Else user_display_name.
   - Else show user_id with a visual badge "unresolved" (e.g. small gray pill next to the truncated UUID).
   - The backend will populate user_display_name from Keycloak resolution.

4. Last-successful-refresh timestamp:
   - Add state lastSuccessAt: Date | null.
   - On successful loadData, set lastSuccessAt = new Date().
   - Display below header: "Last refreshed 2 min ago" (use a relative-time helper) + "Refresh failed — retrying in 60s" overlay when error.

5. Auto-refresh exponential backoff:
   - Replace the fixed 30s setInterval with state currentInterval.
   - On error: currentInterval = Math.min(currentInterval * 2, 300_000).
   - On success: reset to 30_000.
   - Tests: vitest fake timers verifying the interval doubles on consecutive failures.

6. Split-button Export:
   - Replace single Export button with a dropdown: "Export CSV" / "Export JSON".
   - Both call existing endpoints /v1/audit/{tenant_id}/export/{csv|json}.

7. Locale of formatTimestamp:
   - Read locale from useTranslation() i18n hook (or equivalent — check how the existing language switcher works at control-plane-ui/src/components/LanguageSwitcher.tsx or similar).
   - Use d.toLocaleString(locale, ...).

Tests required:
- Backend: pytest --cov=src/services/audit_service.py --cov=src/routers/audit.py with ≥80% coverage on new endpoints.
- Backend: tests/test_regression_cab_XXXX_audit_*.py per fixed emit site.
- Frontend: AuditLog.test.tsx: stats endpoint consumed, actions endpoint consumed, actor unresolved badge appears, exponential backoff math, split-button export.

Acceptance criteria:
- [ ] Production audit_log shows at least one non-chat event after manually triggering an API create.
- [ ] /v1/audit/{tenant_id}/stats endpoint returns aggregates over the filtered window.
- [ ] /v1/audit/{tenant_id}/actions returns distinct actions seen in the dataset.
- [ ] Actor column resolves UUIDs to email/displayName when available, marks unresolved otherwise.
- [ ] Last-refreshed timestamp visible. Refresh failures don't loop at 30s.
- [ ] Demo fallback is OFF in production (verify via env var read at startup, log at INFO).
- [ ] Tests added for all 5 frontend behaviors and 3 backend endpoints.

Out of scope (DO NOT do):
- Schema migration on audit_events table.
- PII erasure UI.
- Cross-tenant aggregation view.
- SWR/TanStack Query refactor.

Commit message format: feat(api,ui): audit log compliance coverage + stats + actor resolution (CAB-XXXX)
```

## Acceptance criteria (binary)

- [ ] Production `/audit-log` shows ≥1 non-chat event after manual API create test.
- [ ] `/v1/audit/{tenant_id}/stats` and `/v1/audit/{tenant_id}/actions` endpoints exist + return correct shape.
- [ ] UI consumes `/stats` for KPIs (no longer "On this page").
- [ ] Actor field shows resolved email/displayName when possible.
- [ ] Last-refreshed timestamp visible.
- [ ] Demo fallback disabled in prod env (verified via startup log).
- [ ] Tests: 3 backend endpoint tests, 5 frontend behavior tests, ≥1 regression test per fixed emit site.

## Tests required from Codex

1. `tests/test_audit_router.py::test_stats_endpoint_returns_aggregates`
2. `tests/test_audit_router.py::test_actions_endpoint_returns_distinct`
3. `tests/test_audit_router.py::test_demo_fallback_disabled_when_env_false`
4. `tests/test_audit_service.py::test_resolve_actor_caches_keycloak_lookup`
5. `tests/test_regression_cab_XXXX_audit_*.py` per emit site fixed
6. `AuditLog.test.tsx::stats endpoint populates KPIs`
7. `AuditLog.test.tsx::actions endpoint populates filter`
8. `AuditLog.test.tsx::actor unresolved badge`
9. `AuditLog.test.tsx::exponential backoff on consecutive errors`
10. `AuditLog.test.tsx::split-button export CSV vs JSON`

## Files probably touched

- `control-plane-api/src/routers/audit.py` (+150 LOC)
- `control-plane-api/src/services/audit_service.py` (+80 LOC)
- `control-plane-api/src/services/keycloak_service.py` (+30 LOC, new resolve helper)
- `control-plane-api/src/config.py` (+1 env var)
- `control-plane-api/tests/test_audit_router.py` (+200 LOC)
- `control-plane-api/tests/test_regression_cab_XXXX_audit_*.py` (multiple new files, ~30 LOC each)
- `control-plane-ui/src/pages/AuditLog.tsx` (~200 LOC modified)
- `control-plane-ui/src/pages/AuditLog.test.tsx` (+150 LOC)
- `control-plane-ui/src/services/api.ts` (~10 LOC, add getStats/getActions methods)

## Risk + dependencies

- **Blocks on PR-1A** (must read findings.md first).
- Keycloak admin API call adds latency to audit list rendering — mitigate with cache + background prefetch.
- If `audit_events` schema lacks `user_display_name`, store it as a transient field in the response, not in DB.

---

# PR-2 — Live Calls Metric Integrity (using `http_route`)

> ✅ **Merged #2727 on 2026-05-07.** PR-2 step 0 evidence (#2720) showed the cause was dashboard-side label mismatch (`path` vs `http_route`), not a gateway emission bug. #2727 migrated Live Calls to `http_route`, aligned metric scope, removed the synthetic heatmap, and kept the real heatmap as a deferred non-blocking follow-up.

**Branch**: `fix/live-calls-http-route-metric-integrity`
**MEGA**: B — Phase 1
**Estimated**: 8 pts, ~250 LOC (frontend only)
**Risk**: medium (cross-cutting on CallFlowDashboard but no backend touch)

## Goal

Make `/observability/live-calls` internally consistent:
- all request KPI and breakdown queries use the same metric scope (`MODE_FILTER`);
- route-level panels group by `http_route`, not `path`;
- synthetic heatmap removed;
- missing route labels rendered as explicit data-state, not as fake routes;
- request metrics and trace availability presented as different pipelines.

## Findings addressed

L1, L2 (root cause: dashboard groups by wrong label), L3, L4, L5, L6, L8, L9, L10.

## Out of scope

- Real heatmap implementation (separate non-blocking ticket post-merge).
- Tempo / Loki / OpenSearch pipeline rewiring.
- AuditLog or Guardrails changes.
- Sidebar / nav cleanup (PR-4).
- Gateway Rust changes (evidence #2720 confirms gateway emits `http_route` correctly).

## Codex prompt

```
You are working on the STOA repository.

Branch: `fix/live-calls-http-route-metric-integrity`

Context:
- Plan: docs/plans/2026-05-07-observability-data-integrity.md
- Original audit: docs/audits/2026-05-07-observability/AUDIT.md
- PR-2 step 0 PromQL evidence: docs/audits/2026-05-08-live-calls-investigation/promql-evidence.md

Important evidence (#2720 merged):
- Current production `stoa_http_requests_total` exposes `http_route` on 306/306 series, `path` on 0/306.
- `stoa_http_request_duration_seconds_bucket` exposes `http_route` on 3627/3627, `path` on 0/3627.
- The audit finding L2 ("path=unknown") is a misdiagnosis: cause is the dashboard groups by the wrong label. Gateway is fine.

Therefore the Live Calls dashboard must use `http_route`, not `path`. Do not investigate Rust gateway path emission in this PR.

Goal: make /observability/live-calls internally consistent.
- all KPI and breakdown queries use the same metric scope (MODE_FILTER);
- route-level panels group by `http_route`;
- synthetic heatmap removed;
- missing route labels rendered as explicit data-state, not fake routes;
- request metrics and trace availability presented as different pipelines.

Files likely involved:
- control-plane-ui/src/pages/CallFlow/CallFlowDashboard.tsx
- control-plane-ui/src/hooks/usePrometheus.ts
- control-plane-ui/src/pages/CallFlow/components/TopRoutes.tsx
- control-plane-ui/src/pages/CallFlow/components/TrafficHeatmap.tsx
- relevant tests under control-plane-ui/src/**/__tests__ or page test locations

Do NOT touch AuditLog or Guardrails in this PR.

---

1. Define metric scope and route label constants

Near the top of CallFlowDashboard.tsx:
  const MODE_FILTER = 'job=~"stoa-gateway|stoa-link|stoa-connect"';
  const ROUTE_LABEL = 'http_route';
  const UNLABELLED_ROUTE = '(unlabelled)';

Use MODE_FILTER consistently. Use ROUTE_LABEL for grouping. Do not use `path` for current route-level panels.

2. Align all Live Calls Prometheus query scopes

All queries on `stoa_http_requests_total` and `stoa_http_request_duration_seconds_bucket` must use:
  {job=~"stoa-gateway|stoa-link|stoa-connect"}

Examples:
  sum(increase(stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}[$range]))
  sum by (job) (increase(stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}[$range]))

For histogram route-level latency (evidence confirms `http_route` is on 3627/3627 series):
  topk(8, histogram_quantile(0.95, sum by (le, http_route) (rate(stoa_http_request_duration_seconds_bucket{job=~"stoa-gateway|stoa-link|stoa-connect", http_route!="", http_route!="unknown"}[5m]))))

3. Replace route grouping from `path` to `http_route`

Anywhere code currently does `metric.path`, `groupByLabel(..., 'path')`, or `sum by (path)`, switch to `metric.http_route`, `groupByLabel(..., 'http_route')`, or `sum by (http_route)`.

Do not keep a `path` fallback unless a test proves older environments need it. If a fallback is required, it must be explicit:
  const route = metric.http_route ?? metric.path ?? UNLABELLED_ROUTE;

But current production should prefer `http_route`.

4. Replace `'unknown'` fallback with explicit unlabelled semantics

In src/hooks/usePrometheus.ts, change:
  const key = r.metric[label] || 'unknown';
to:
  const raw = r.metric[label];
  const key = raw && raw.trim() ? raw : '(unlabelled)';

Empty strings and missing labels both treated as unlabelled.

5. Top Routes behavior

Top Routes must NEVER render a normal route called `unknown` or `(unlabelled)`.

- If at least one valid http_route exists: filter out unknown/empty/(unlabelled) and render valid routes.
- If all route data is missing/unlabelled: render an EmptyState:
  "Route labels unavailable. Metrics currently do not expose a usable `http_route` label for route-level panels. Check Prometheus scrape config and gateway instrumentation."
- If no route data at all: render the existing no-data state with clear wording.

Do not show a fake single-row Top Routes table.

6. Remove synthetic heatmap

Delete the deterministic hash + business-hours block in CallFlowDashboard.tsx (the heatmap synthesis around the `hash()` and `flatMap` over 24 hours).

Replace with an EmptyState:
  "Traffic heatmap unavailable. A real range-query heatmap is not wired yet for the selected time range."

Add a TODO consistent with repo style:
  // TODO: implement real heatmap with Prometheus query_range grouped by http_route (separate ticket).

Do NOT implement the real heatmap in this PR.

7. Fix Active Modes query

Active Modes must count deployment modes/jobs, not route labels:
  count(count by (job) (stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}))

If product label stays "Active Modes", subtitle should say "Gateway / Link / Connect jobs reporting traffic". Do NOT count `path` or `http_route` for this KPI.

8. Add scope-mismatch banner

When totalRequests > 0 AND all Gateway/Link/Connect breakdowns are 0/missing, show an amber banner:
  "Total requests are available, but no Gateway/Link/Connect breakdown traffic was found for the selected window. Some scraped series may not match the expected job scope."

Regression guard for the original bug. May not appear in normal production after MODE_FILTER alignment, but keep the logic and test it with mocked data.

9. Clarify traces empty state

When request metrics are non-zero but `/v1/monitoring/transactions` returns empty:
  "Request metrics are available, but no traces were found for this time range. Metrics source: Prometheus. Trace source: Tempo/OpenSearch pipeline."

Do not imply the entire observability pipeline is healthy.

10. Header sanity check

PR-0 already changed the h1 to "Live Calls". Verify this remains true. Do not touch route/nav/sidebar in this PR.

---

Tests required (use existing test setup):

a. Query label test: route-level queries use `http_route`, not `sum by (path)` or `metric.path`.
b. groupByLabel fallback test: missing/empty label → `(unlabelled)`, never `unknown`.
c. Top Routes unlabelled test: 100% unlabelled → EmptyState, not a normal row.
d. Top Routes valid test: mix of valid and unlabelled → unlabelled filtered out.
e. Synthetic heatmap removal test: heatmap no longer generates cells from deterministic hash; with no real heatmap data, renders EmptyState.
f. Scope mismatch banner test: total > 0 + breakdowns = 0 → banner appears.
g. Traces split-brain test: total > 0 + transactions = [] → "metrics available, traces not found".

Commands (from control-plane-ui):
  npm run lint
  npm run test -- --run
  npm run test -- --run src/pages/CallFlow
  npm run test -- --run src/hooks/usePrometheus.test.ts

---

Acceptance criteria:
- All Live Calls request queries use a consistent MODE_FILTER.
- Route-level panels use `http_route`, not `path`.
- No normal UI row called `unknown` or `(unlabelled)` is shown as a route.
- When route labels unavailable, explicit EmptyState rendered.
- Synthetic heatmap removed.
- Active Modes counts `job`, not routes.
- Scope mismatch banner exists and is tested.
- Live Traces distinguishes Prometheus metrics from Tempo/OpenSearch traces.
- No AuditLog changes.
- No Guardrails changes.
- No backend endpoint changes.
- Lint and tests pass.

Out of scope (do NOT do):
- Real heatmap implementation.
- Tempo/OpenSearch ingestion changes.
- AuditLog or Guardrails modifications.
- Sidebar/nav legacy cleanup.
- Audit stats/actions endpoints.
- Audit Kafka consumer restore (PR-1A2 handles that).

Commit message: fix(ui): align live calls metrics on http_route

PR title: fix(ui): align live calls metrics on http_route

PR body must include:
## Summary
Fixes Live Calls metric integrity based on the PR-2 step 0 PromQL evidence.

Evidence:
- current `stoa_http_requests_total` series expose `http_route` on 306/306 series
- `path` is absent on 0/306 series

Changes:
- align Live Calls metric scope across KPI and breakdowns
- use `http_route` for route-level panels
- remove synthetic heatmap
- add explicit route-label unavailable state
- add scope-mismatch banner
- clarify Prometheus metrics vs traces empty state

## Non-goals
- no real heatmap implementation
- no Tempo/OpenSearch rewiring
- no AuditLog changes
- no Guardrails changes
- no sidebar cleanup

## Tests
- [ ] npm run lint
- [ ] npm run test -- --run
- [ ] route-level queries use `http_route`
- [ ] unlabelled routes do not render as normal rows
- [ ] synthetic heatmap removed
- [ ] scope mismatch banner
- [ ] traces split-brain empty state
```

## Acceptance criteria (binary)

- [ ] `docs/audits/2026-05-08-live-calls-investigation/promql-evidence.md` exists.
- [ ] All 7 page queries use the same MODE_FILTER constant.
- [ ] `'unknown'` no longer appears in the UI; replaced by `'(unlabelled)'` semantics + EmptyState.
- [ ] Heatmap synthetic code deleted; placeholder EmptyState shown.
- [ ] Scope-mismatch banner test passes.
- [ ] Active Modes query corrected OR renamed.

## Tests required from Codex

1. `live-calls-scope-mismatch.test.tsx` — banner appears when KPI > 0 + breakdowns = 0.
2. `live-calls-unlabelled-routes.test.tsx` — EmptyState when 100% unlabelled.
3. `TopRoutes.test.tsx` — empty state.
4. `live-calls-no-synthetic-heatmap.test.tsx` — heatmapCells empty.
5. `usePrometheus.test.ts` — `'(unlabelled)'` fallback.
6. (Conditional) `cargo test record_http_request_always_has_path_label`

## Files probably touched

- `control-plane-ui/src/hooks/usePrometheus.ts` (1 line + tests)
- `control-plane-ui/src/pages/CallFlow/CallFlowDashboard.tsx` (~120 LOC modified)
- `control-plane-ui/src/pages/CallFlow/components/TopRoutes.tsx` (~30 LOC, empty state)
- `control-plane-ui/src/pages/CallFlow/components/TrafficHeatmap.tsx` (potential, ~10 LOC)
- 5 new test files
- (Conditional) `stoa-gateway/src/lib.rs` (~10 LOC + cargo test)
- `docs/audits/2026-05-08-live-calls-investigation/promql-evidence.md` (new)

## Risk + dependencies

- Investigation step requires real production token (CPI Admin).
- Gateway change conditional sur evidence — codex doit DECIDER en step 0, pas faire les deux.
- Coordination potentielle avec gateway team si fix Rust.

---

# PR-3 — Security & Guardrails Runtime Truth

**Branch**: `feat/guardrails-runtime-truth`
**MEGA**: B — Phase 2
**Estimated**: 8 pts, ~250 LOC
**Risk**: medium (depends on AR-1, AR-2)
**Contract**: PR-3 implementation must follow `docs/plans/2026-05-10-guardrails-runtime-truth-contract.md`, which elaborates Annex B and preserves AR-1/AR-2.

## Goal

Faire en sorte que `/observability/security` ne ment plus: les counts à 0 doivent distinguer "désactivé/activé/stale/error", la config doit afficher l'état réel ON/OFF (pas juste les noms d'env vars), un time range selector aligné sur Live Calls.

## Findings addressed

S2, S3, S4, S5 (couper le sous-titre), S8 (après AR-1), S9 (sidebar — délégué PR-4).

## Out of scope

- Décision IA Security Posture vs Guardrails (AR-1 traité avant).
- Sidebar cleanup (PR-4).

## Codex prompt

```
You are working on STOA control-plane-api and control-plane-ui.

PRECONDITION: read docs/plans/2026-05-07-observability-data-integrity.md (section 'Arbitrages requis') and docs/plans/2026-05-10-guardrails-runtime-truth-contract.md. If AR-1 (Security Posture vs Security & Guardrails) is not yet decided, or if the PR-3A contract is missing/not validated, STOP and request decision before proceeding.

Goal: make /observability/security display real runtime state.

Backend tasks (control-plane-api/src/):

1. Add new endpoint GET /v1/admin/gateways/guardrails/config.
   Response shape:
     class GuardrailsConfigResponse(BaseModel):
         pii_enabled: bool
         injection_detection_enabled: bool
         prompt_guard_enabled: bool
         content_filter_enabled: bool
         rate_limit_enabled: bool
         opa_policy_enabled: bool
         source: Literal["env", "runtime", "config-service"]
         updated_at: datetime
   Implementation: read from the same source the gateway uses at runtime (likely env vars or a config endpoint on the gateway itself). If unsure, query the gateway /admin/config endpoint or expose the cp-api known state.

2. Extend /v1/admin/gateways/metrics response (or sibling endpoint) to include freshness:
     class GuardrailMetrics(BaseModel):
         pii_detections: int | None
         injection_blocks: int | None
         prompt_guard_blocks: int | None
         content_filter_blocks: int | None
         rate_limit_blocks: int | None
         last_sample_at: datetime | None
         metrics_age_seconds: int | None
         source_healthy: bool
   IMPORTANT: use None (null) for unknown values, not 0. The frontend distinguishes "0 events with healthy source" from "no data".

Frontend tasks (control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.tsx):

1. Replace the env-var-name-only ConfigRow with real ON/OFF rendering:
     <ConfigRow label="PII Detection" enabled={config.pii_enabled} />
     <ConfigRow label="Injection Protection" enabled={config.injection_detection_enabled} />
     ...
   ConfigRow must show "Enabled" / "Disabled" with green/gray pills.
   Keep the env var name as a secondary tooltip/diagnostic detail (smaller, gray).

2. Card rendering rules:
   - source_healthy=true, count=0 → "0 events · last sample 12s ago" (relative time).
   - source_healthy=true, count>0 → normal count.
   - enabled=false → "Disabled" badge replacing the count.
   - last_sample_at=null → "No metrics sample".
   - metrics_age_seconds > 60 → "Stale metrics · last sample 47m ago".
   - source_healthy=false → "Metrics unavailable" with red icon.

3. Add TimeRangeSelector component (reuse from src/components/TimeRangeSelector or @stoa/shared) with the same model as Live Calls (1h/6h/24h/7d).
   Pass selected range to the metrics + events fetches.

4. Update subtitle to match what the page actually delivers. If OPA policy events are NOT in scope of this PR, remove "policy decisions" from the subtitle.

5. Remove the synthetic 'all'-filter on Rate Limit card (already done in PR-0). Verify here.

6. Trace navigation should already use /observability/live-calls/trace/... (PR-0). Verify.

Tests required:

Backend:
- tests/test_gateway_observability_router.py — new endpoint /guardrails/config returns correct shape.
- tests/test_gateway_observability_router.py — metrics endpoint returns null vs 0 distinction.

Frontend:
- GuardrailsDashboard.test.tsx — config panel renders Enabled/Disabled badges, not just env var names.
- GuardrailsDashboard.test.tsx — card distinguishes 5 states (healthy+0, healthy+N, disabled, no-sample, stale, error).
- GuardrailsDashboard.test.tsx — TimeRangeSelector changes metrics fetch query.

Acceptance criteria:
- [ ] Config panel shows real Enabled/Disabled state.
- [ ] Cards distinguish disabled vs zero vs stale vs error.
- [ ] Time range selector exists and propagates.
- [ ] Subtitle matches delivered content.
- [ ] Tests for 5 card states + config rendering.

Out of scope:
- Security Posture page changes.
- Sidebar entries (PR-4).

Commit message: feat(api,ui): security & guardrails runtime truth — config + freshness + time range (CAB-XXXX)
```

## Acceptance criteria (binary)

- [ ] `/v1/admin/gateways/guardrails/config` endpoint exists with real ON/OFF values.
- [ ] Metrics endpoint returns `null` for unknown, not silent 0.
- [ ] UI distinguishes 5+ states (healthy+0, healthy+N, disabled, no-sample, stale, error).
- [ ] TimeRangeSelector cohérent avec Live Calls.
- [ ] Tests pour les 5 états + config rendering.

## Tests required from Codex

1. `tests/test_gateway_observability_router.py::test_guardrails_config_endpoint`
2. `tests/test_gateway_observability_router.py::test_metrics_null_vs_zero`
3. `GuardrailsDashboard.test.tsx::config_panel_real_state`
4. `GuardrailsDashboard.test.tsx::card_state_distinguishes_disabled_zero_stale_error` (×5 states)
5. `GuardrailsDashboard.test.tsx::time_range_selector_propagates`

## Files probably touched

- `control-plane-api/src/routers/gateway_observability.py` (+80 LOC)
- `control-plane-api/src/services/gateway_service.py` (+30 LOC)
- `control-plane-api/src/schemas/guardrails.py` (new, ~50 LOC)
- `control-plane-api/tests/test_gateway_observability_router.py` (+100 LOC)
- `control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.tsx` (~80 LOC modified)
- `control-plane-ui/src/pages/GatewayGuardrails/GuardrailsDashboard.test.tsx` (+150 LOC)
- `control-plane-ui/src/services/api.ts` (+5 LOC)

## Risk + dependencies

- **Blocks on AR-1, AR-2** (arbitrage produit).
- Source of guardrails config truth peut être Rust gateway (besoin endpoint admin).
- Coordination potentielle avec gateway team.

---

# PR-4 — Navigation IA cleanup

**Branch**: `chore/observability-nav-cleanup`
**MEGA**: B — Phase 3
**Estimated**: 3 pts, ~80 LOC
**Risk**: low (after AR-1)

## Goal

Retirer les entrées sidebar legacy qui pointent vers des routes redirigées, clarifier la coexistence Security Posture vs Security & Guardrails dans la nav.

## Findings addressed

S8 (après AR-1), S9, partiel L8.

## Codex prompt

```
You are working on STOA control-plane-ui.

PRECONDITION: AR-1 must be decided in docs/plans/2026-05-07-observability-data-integrity.md (section 'Arbitrages requis'). Read it first.

Goal: clean up sidebar navigation post-PR #2713 consolidation.

Tasks:

1. Identify the sidebar component (likely src/components/Layout.tsx or src/components/Sidebar.tsx).

2. Remove sidebar entries that ONLY redirect to a current page:
   - "Gateway → Security" (/gateway-security) — redirects to /observability/security.
   - "Gateway → Guardrails" (/gateway-guardrails) — redirects to /observability/security.
   Both legacy redirects must REMAIN in App.tsx routing for backwards compatibility (deep links from external dashboards), but they should NOT be advertised in the sidebar.

3. Per AR-1 decision, either:
   (a) Keep "Security Posture" under Governance separate from "Security & Guardrails" under Observability — add explicit subtitle on each page distinguishing scopes:
       - Security Posture: "Compliance findings, security score, configuration assessment"
       - Security & Guardrails: "Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring"
   OR
   (b) Merge them into one page if AR-1 chose merge. (NOT RECOMMENDED — see AR-1.)

4. Add a regression test src/__tests__/regression/sidebar-no-legacy-redirects.test.tsx asserting no sidebar link href starts with '/gateway-security' or '/gateway-guardrails'.

5. Add per-route h1↔breadcrumb regression tests for the 3 audited pages:
   - /observability/live-calls → "Live Calls"
   - /audit-log → "Audit Log"
   - /observability/security → "Security & Guardrails"
   Use Playwright or react-testing-library with the existing test infrastructure.

Acceptance:
- [ ] No sidebar link to /gateway-security or /gateway-guardrails.
- [ ] Legacy redirects still work (deep link tests).
- [ ] Per AR-1, IA clarification applied.
- [ ] Regression tests added.

Out of scope:
- DO NOT remove legacy routes from App.tsx (only nav entries).
- DO NOT touch CallFlow / Guardrails / AuditLog page logic.

Commit message: chore(ui): observability sidebar cleanup — remove legacy redirected entries (CAB-XXXX)
```

## Acceptance criteria (binary)

- [ ] No active sidebar entry points to `/gateway-security` or `/gateway-guardrails`.
- [ ] Legacy redirects in App.tsx still functional (deep-link test).
- [ ] Per AR-1, IA decision applied (subtitles or merge).
- [ ] Regression tests for sidebar + h1↔breadcrumb.

## Tests required from Codex

1. `sidebar-no-legacy-redirects.test.tsx`
2. `observability-titles.test.ts` (extension to AuditLog already covered in PR-0).

## Files probably touched

- `control-plane-ui/src/components/Layout.tsx` or `Sidebar.tsx` (~30 LOC)
- `control-plane-ui/src/__tests__/regression/sidebar-no-legacy-redirects.test.tsx` (new, ~30 LOC)
- `control-plane-ui/src/__tests__/regression/observability-titles.test.ts` (extension, ~20 LOC)

## Risk + dependencies

- **Blocks on AR-1** (arbitrage produit IA).
- **Blocks on PR-3 merge** (subtitle text dépend du contenu PR-3).

---

# Linear ticket structure (proposed)

Updated 2026-05-08 after PR-1A4 incident, PR-1A5 evidence (#2733), and A1b activation state. MEGA-A grew to 7 phases.

```
[Standalone chore — DONE]
└── PR-0 — Observability quick wins (1pt) — #2717 merged 2026-05-07

[MEGA-A: Audit Log Data Integrity] (~32pt, 7 phases)
├── Phase 1 — PR-1A   Investigation (3pt) — #2721 merged 2026-05-08, BLOCKED verdict
├── Phase 2 — PR-1A2  Consumer restore scope (1pt) — #2723 merged 2026-05-08, Case C
├── Phase 3 — PR-1A3  Audit ingestion contract mini-spec (3pt, docs-only) — #2724 merged, validated
├── Phase 4 — PR-1A4  Audit consumer implementation (8pt, backend + manifest) — #2726 + #2730/#2734 corrective, image deployed
├── Phase 5 — PR-1A5  Verification evidence (2pt, post-deploy proof) — #2733 data-path PASS, caveat continuous ingestion was off
├── Phase 6 — PR-1A6  Activation A1b + post-activation evidence amend (2pt) — stoa-infra #75 chart flip merged; evidence amend pending
└── Phase 7 — PR-1B   Audit Log API + UI (13pt, gated on PR-1A6 PASS)

[MEGA-B: Runtime Observability Data Integrity] (21pt, 3 phases)
├── Phase 1 — PR-2 Live Calls metric integrity (8pt) — #2727 merged
├── Phase 2 — PR-3 Security & Guardrails runtime truth (8pt, BLOCKED on Annex B)
└── Phase 3 — PR-4 Sidebar IA cleanup (5pt, BLOCKED on AR-1+PR-3)
```

## PR-1A2 — Audit consumer restore/scope (DONE)

**Status**: ✅ Merged #2723 on 2026-05-08. Verdict `CONSUMER_IMPLEMENTATION_NOT_FOUND` (Case C). Evidence: `docs/audits/2026-05-08-audit-consumer-restore/scoping.md`.

At PR-1A2 time, the repository contained Kafka audit producers and 5 generic consumer patterns, but no audit consumer implementation that persisted `stoa.audit.trail`/`audit-log`/`stoa.audit.events` into PostgreSQL `audit_events`. Building a consumer was **new ingestion architecture, not a restore** — hence the explicit insertion of PR-1A3 (mini-spec) -> PR-1A4 (implementation) -> PR-1A5 (verification), later extended with PR-1A6 (activation + post-activation evidence amend) before PR-1B can start.

The codex prompt that produced this PR is preserved in git history (commit on `fix/audit-consumer-restore` branch, merged squash). It is no longer reproduced in this plan to avoid redundancy.

## PR-1A3 — Audit ingestion contract mini-spec (DONE, validated)

**Status**: ✅ Merged #2724 on 2026-05-07, validated. Output:
`docs/plans/2026-05-08-audit-consumer-ingestion-contract.md`
(frontmatter `validation_status: validated`).

**Scope shipped** (covers and extends the 8 sections originally planned):

| Section | Decision in #2724 |
|---|---|
| Canonical topic | `stoa.audit.trail` (active producer); `audit-log` and `stoa.audit.events` left as legacy/unmanaged for now (deferred to open question 1). |
| Source-of-truth | Implicitly (b) Kafka → PostgreSQL via the new consumer. Direct `AuditService.record_event(...)` paths preserved (chat, governance) — not replaced. |
| Consumer group | `audit-trail-pg-consumer`, `auto_offset_reset=earliest`, **manual commits only**. |
| Payload schema | Maps current `KafkaService._create_event(...)` envelope; required vs optional fields enumerated; missing required → DLQ. |
| Idempotency | `event.id` → `audit_events.id`; duplicate = no-op (commit offset). |
| Failure / DLQ | DLQ topic `stoa.audit.trail.dlq`, retry capped 60s, no auto-commit, schema/programming errors do not DLQ. |
| Observability | 6 named Prometheus metrics, structured log fields specified, 3 alert intents. |
| Deployment model | (a) In-process worker in cp-api, gated by `STOA_ENABLE_KAFKA_CONSUMERS` master + `ENABLE_AUDIT_TRAIL_CONSUMER` per-consumer. Mini-spec default was `true`; #2730 corrected implementation default to fail-closed `"false"` after the PR-1A4 incident. |
| Backfill | `earliest` on first deploy; no PG/OpenSearch/log-based backfill; no replay older than Kafka retention. |

**Bonus content not in original prompt** (worth keeping):
- Ordering guarantees (partition-only, `created_at` from envelope timestamp).
- Tenant isolation rules (reject empty/`unknown`, no inference).
- Producer-side PII masking preserved + tested.
- Rollout 10 steps with explicit dev → prod gating.
- Verification SQL + `rpk` commands ready to copy.
- 5 open questions deferred (audit-log deletion, AUDIT_EVENTS deprecation, separate Deployment, future producer fields, DLQ retention).

**Validation gate**: completed by #2724; PR-1A4 was unblocked after merge.

**No new codex prompt is needed for PR-1A3** — codex has already produced the deliverable. The original prompt that drove it is preserved in git history on the `docs/audit-consumer-ingestion-contract` branch.

## PR-1A4 — Audit consumer implementation (DONE, backend + manifest)

**Branch**: `feat/audit-consumer-implementation`
**MEGA**: A — Phase 4
**Estimated**: 8 pts, ~400 LOC (Python consumer + Helm/k8s + tests)
**Risk**: medium (new runtime workload + production data path)

**Status**: ✅ #2726 merged 2026-05-07 18:39 UTC. Corrective #2730 merged 19:08 UTC to change code/base-manifest default from `"true"` to `"false"`. Test fix #2734 merged 2026-05-08 06:30 UTC to replace the `importlib.reload(main)` regression test that hung CI. Post-fix image `dev-1803ef125...` deployed to OVH prod.

### Goal

Implement the audit consumer per the mini-spec locked in PR-1A3. Land deployable code + manifest. Do NOT modify the AuditLog UI/API surface yet.

### Codex prompt

```
You are working on the STOA repository.
Branch: `feat/audit-consumer-implementation`

Context:
- Plan: docs/plans/2026-05-07-observability-data-integrity.md
- Mini-spec: docs/plans/2026-05-08-audit-consumer-ingestion-contract.md  (PR-1A3)
- PR-1A evidence: docs/audits/2026-05-08-audit-ingestion/findings.md
- PR-1A2 scoping: docs/audits/2026-05-08-audit-consumer-restore/scoping.md

PRECONDITION: read docs/plans/2026-05-08-audit-consumer-ingestion-contract.md first. If the mini-spec is not on main yet, STOP and request that PR-1A3 be merged before proceeding.

Goal: implement the audit consumer per the mini-spec.

Tasks:

1. Implement the consumer
   - Follow the existing Kafka consumer patterns:
     control-plane-api/src/consumers/deployment_consumer.py
     control-plane-api/src/consumers/promotion_deploy_consumer.py
     control-plane-api/src/workers/chat_metering_consumer.py
   - Place the new file at control-plane-api/src/consumers/audit_trail_consumer.py
     (or similar, consistent with the mini-spec).
   - Subscribe to the canonical topic chosen by the mini-spec.
   - Use the consumer group name from the mini-spec.
   - Use the offset policy from the mini-spec.
   - Persist to PostgreSQL audit_events with ON CONFLICT (id) DO NOTHING semantics per the mini-spec.

2. Wire startup gate
   - Add `ENABLE_AUDIT_TRAIL_CONSUMER` env var (fail-closed default false after #2730; activation via chart values only).
   - Update control-plane-api/src/main.py to start the audit consumer task when the gate is on.
   - Update tests/test_regression_kafka_boot.py to include the new consumer flag.

3. Failure mode + observability
   - Producer-side audit failures must NOT raise to user-facing operation.
   - Consumer-side: failed PG insert → log WARN, retry per mini-spec, then DLQ topic.
   - Add Prometheus metrics: stoa_audit_consumer_lag, stoa_audit_consumer_errors_total, stoa_audit_consumer_processed_total.
   - Structured log on every consume cycle (count, last offset).

4. Helm/Kubernetes manifest
   - Either (a) add ENABLE_AUDIT_TRAIL_CONSUMER=true to existing cp-api Deployment env, or
     (b) add a separate Deployment for stoa-audit-consumer.
   - Match the mini-spec deployment-model decision.
   - Manifest path: charts/stoa-platform/templates/... or control-plane-api/k8s/...

5. Backfill
   - Implement the mini-spec backfill strategy (typically: first deploy, offset=earliest with a clear log "starting backfill from offset X").
   - Document the dual-write window risk in the PR description.

Tests required:

- Unit test: consumer parses Kafka envelope and inserts correct audit_events row (use httpx.MockTransport-style boundary or asyncpg test fixture per repo standard).
- Unit test: idempotency — same envelope.id processed twice does NOT insert twice.
- Unit test: malformed envelope → DLQ + WARN log, no exception bubbles.
- Integration test: consumer registers on topic, commits offset (skip if --integration not enabled).
- Regression test: tests/test_regression_kafka_boot.py asserts ENABLE_AUDIT_TRAIL_CONSUMER is fail-closed by default and only enables with explicit env.

Acceptance criteria:
- [ ] Consumer subscribes to canonical topic (mini-spec).
- [ ] PostgreSQL audit_events inserts succeed with idempotency.
- [ ] DLQ on failures, no user-facing impact.
- [ ] Manifest deployable (helm template renders, kubectl --dry-run=client passes).
- [ ] Tests pass.
- [ ] PR body includes: link to mini-spec, deployment-model decision, backfill strategy.

Out of scope (DO NOT do):
- AuditLog UI/API changes (PR-1B).
- /v1/audit/{tenant_id}/stats or /actions.
- audit_events schema migration.
- Topic rename/migration (the mini-spec decided one canonical topic; renames are separate).
- Demo data fallback removal (already decided in AR-3, lands in PR-1B).

Commit message: feat(api,infra): audit consumer implementation per mini-spec (PR-1A4)

PR title: feat(api,infra): audit consumer implementation

PR body must reference:
- Plan: docs/plans/2026-05-07-observability-data-integrity.md
- Mini-spec: docs/plans/2026-05-08-audit-consumer-ingestion-contract.md
- Deployment model chosen (a or b from mini-spec) with one-line justification.
```

### Acceptance criteria (binary)

- [ ] Consumer code in `control-plane-api/src/consumers/...` per mini-spec.
- [x] `ENABLE_AUDIT_TRAIL_CONSUMER` env var wired (main.py + boot regression test; default corrected to `"false"` by #2730).
- [ ] Manifest deployable (helm template / kubectl --dry-run pass).
- [ ] Idempotency proven by unit test.
- [ ] DLQ on failure proven by unit test.
- [ ] Prometheus metrics emitted.
- [ ] No AuditLog UI/API surface changes.

### Files probably touched

- `control-plane-api/src/consumers/audit_trail_consumer.py` (new, ~150 LOC)
- `control-plane-api/src/main.py` (~10 LOC for gate)
- `control-plane-api/src/services/kafka_service.py` (potentially ~10 LOC if topic constant changes per mini-spec)
- `control-plane-api/tests/test_audit_trail_consumer.py` (new, ~150 LOC)
- `control-plane-api/tests/test_regression_kafka_boot.py` (~5 LOC)
- `charts/stoa-platform/templates/...` or `control-plane-api/k8s/...` (~30 LOC)

### Risk + dependencies

- **Blocks on PR-1A3 merge** (mini-spec must be on main).
- Production data write path — coordinate with infra for first deploy.
- Backfill window: monitor consumer lag closely after deploy.

## PR-1A5 — Verification evidence (DONE, post-deploy proof)

**Branch**: `docs/audit-consumer-runtime-verification`
**MEGA**: A — Phase 5
**Estimated**: 2 pts, docs-only (evidence pack)
**Risk**: low (read-only, post-deploy verification)

**Status**: ✅ #2733 merged 2026-05-08. Data-path PASS while the consumer was enabled: event `b9ca45fb-67b3-4823-98af-c198c3d68871` advanced Kafka offset `30018 -> 30019`, persisted into `audit_events`, and appeared in `/v1/audit/demo`. Caveat: consumer was disabled by config at the end of the evidence window; PR-1B remains blocked until PR-1A6 post-activation evidence confirms continuous ingestion while enabled.

### Goal

Prove that the PR-1A4 consumer is operational in production by demonstrating that **at least one non-chat audit event** appears in `/v1/audit/{tenant_id}` after a manual API mutation. This is the canonical **PR-1B unblock signal**.

### Codex prompt

```
You are an SRE running a read-only verification in production.

Branch: `docs/audit-ingestion-verification-2026-05-XX` (replace XX with actual date)

Context:
- Plan: docs/plans/2026-05-07-observability-data-integrity.md
- Mini-spec: docs/plans/2026-05-08-audit-consumer-ingestion-contract.md (PR-1A3)
- Implementation: PR-1A4 merged + deployed to OVH prod

Goal: prove the consumer is operational and produce an evidence pack at
  docs/audits/2026-05-XX-audit-ingestion-verification/proof.md

Required sections in proof.md:

## 1. Pre-state inventory
- audit_events row count BEFORE the manual mutation.
- audit_events newest row timestamp BEFORE.
- Consumer group `audit-events-consumer` (or canonical name) lag BEFORE.
Run from prod kubeconfig:
  KUBECONFIG=$HOME/.kube/config-stoa-ovh kubectl exec ...

## 2. Manual mutation
Trigger ONE non-chat audit-emitting operation, e.g.:
- POST /v1/tenants (create a test tenant)
- PUT /v1/apis/{id} (update an API)
- POST /v1/deployments (trigger a deployment)
Document the command, the response body (sanitize tenant secrets), and the timestamp.

## 3. Consumer activity
Within 30 seconds, verify:
- Kafka consumer group lag dropped to zero (or by N if N events emitted).
- audit_events row count increased.
- New row visible with action != chat_*.

## 4. UI verification
Hit /v1/audit/{tenant_id} via the cp-api directly:
  curl -s -H "Authorization: Bearer ${TOKEN}" \
    https://api.gostoa.dev/v1/audit/{tenant_id}?page=1&page_size=20 \
    | jq '.entries[] | select(.action != "chat_conversation_create" and .action != "chat_tool_call")'
Document the JSON output (sanitize tenant secrets).

## 5. Verdict
- PASS / FAIL with evidence.
- If FAIL: describe what was missing (lag stuck, audit_events not incremented, action absent in /v1/audit).
- If PASS while consumer is continuously enabled after A1b activation: PR-1B is now unblocked. Update plan section "PR-1B BLOCKED notice" to reflect.

DO NOT:
- Mutate production data beyond the single test mutation.
- Skip the cleanup of the test tenant/API/deployment.
- Print raw secrets or tenant credentials in the evidence pack.
- Use a non-prod environment unless the prod cp-api is unavailable (document if so).

Acceptance:
- [ ] Pre-state inventory captured.
- [ ] Manual mutation triggered and timestamped.
- [ ] Consumer activity proven (lag, audit_events delta).
- [ ] /v1/audit/{tenant_id} returns ≥1 non-chat row from this mutation.
- [ ] Verdict is PASS, OR FAIL with explicit gap analysis.

Commit message:
  docs(observability): audit ingestion verification proof — PASS   (success)
  docs(observability): audit ingestion verification proof — FAIL <gap>  (failure)

PR title: same as commit message.

PR body must reference:
- Plan: docs/plans/2026-05-07-observability-data-integrity.md
- Mini-spec: docs/plans/2026-05-08-audit-consumer-ingestion-contract.md
- Implementation: PR-1A4 (link)
- Verdict: PASS / FAIL.
```

### Acceptance criteria (binary)

- [ ] `docs/audits/2026-05-XX-audit-ingestion-verification/proof.md` with 5 sections.
- [ ] Single manual mutation documented and cleaned up.
- [ ] Consumer activity proven (lag dropped, audit_events incremented, /v1/audit returns the row).
- [ ] Verdict PASS or FAIL.
- [ ] **PASS after A1b continuous-ingestion check** unblocks PR-1B; **FAIL** keeps PR-1B blocked and triggers a follow-up on PR-1A4/PR-1A6.

### Files probably touched

- `docs/audits/2026-05-09-audit-consumer-verification/findings.md` (new evidence pack in #2733)
- (no source change)

### Risk + dependencies

- **Blocks on PR-1A4 merge + production deploy**.
- Requires kubeconfig OVH prod read-only + a usable CPI Admin token for `/v1/audit/{tenant_id}` HTTP probe.
- Test mutation must be cleaned up after evidence is captured (delete the test tenant/API/deployment).

## PR-1A6 — Activation A1b + post-activation evidence amend (NEW phase)

**Branch**: stoa-infra #75 for chart flip; follow-up stoa docs branch for evidence amend
**MEGA**: A — Phase 6
**Estimated**: 2 pts (1pt chart flip + 1pt evidence amend)
**Risk**: low/medium (runtime activation of already-implemented Kafka -> PostgreSQL consumer)

### Goal

Activate `ENABLE_AUDIT_TRAIL_CONSUMER` through the prod-effective stoa-infra chart values, then amend the STOA evidence pack to prove continuous ingestion while enabled. This phase is the new PR-1B gate after the PR-1A4 unsafe-default incident.

### Scope

- stoa-infra #75 chart flip: `charts/control-plane-api/values.yaml` changes `ENABLE_AUDIT_TRAIL_CONSUMER` from `"false"` to `"true"`.
- stoa evidence amend: update `docs/audits/2026-05-09-audit-consumer-verification/findings.md` or add a follow-up evidence file.
- Evidence must include the same signal as PR-1A5, but after activation: group `audit-trail-pg-consumer` `STATE=Stable`, `MEMBERS>=1`, acceptable lag, a controlled non-chat mutation, PostgreSQL row, and `/v1/audit/{tenant_id}` visibility.

### Current status

- stoa-infra #75 was originally DRAFT/HOLD with explicit operator-go requirement.
- Verified 2026-05-08: #75 is merged and prod Deployment renders `ENABLE_AUDIT_TRAIL_CONSUMER="true"`.
- Read-only prod check during this plan update: image `dev-1803ef125...`, group `audit-trail-pg-consumer` `STATE=Stable`, `MEMBERS=1`, `TOTAL-LAG=0`, offset `30054`.
- The evidence amend is still pending; PR-1B remains blocked until the amend records `PR-1B_UNBLOCKED`.

### Acceptance criteria

- [x] stoa-infra #75 merged after explicit operator go.
- [x] Prod Deployment renders `ENABLE_AUDIT_TRAIL_CONSUMER="true"`.
- [ ] Evidence pack amended with `**VERDICT: PR-1B_UNBLOCKED — continuous ingestion verified <UTC timestamp>.**`
- [ ] The amended evidence shows a non-`chat_*` row visible via `/v1/audit/{tenant_id}` after a manual API mutation while the consumer is continuously enabled.

# Sequencing (real timeline)

Updated 2026-05-08 after PR-1A4 incident, #2733 evidence, and A1b activation state. MEGA-A audit chain is now 7 phases instead of 2.

```
Day 0 — 2026-05-07 (DONE):
  - PR-0 quick wins (#2717 merged 12:56 UTC).
  - Plan + audit canon (#2718 merged 12:57 UTC).
  - AR-1..AR-6 fill (#2719 merged 13:09 UTC).
  - PR-2 step 0 PromQL evidence (#2720 merged 14:49 UTC).
  - PR-1A audit ingestion findings (#2721 merged 14:54 UTC).
  - Plan investigation results update (#2722 merged 16:55 UTC).
  - PR-1A2 audit consumer restore scope (#2723 merged 17:23 UTC, Case C).
  - PR-1A3 audit consumer ingestion contract (#2724 merged 17:49 UTC, validated).
  - PR-2 Live Calls http_route migration (#2727 merged 18:27 UTC).
  - PR-1A4 audit consumer implementation (#2726 merged 18:39 UTC).
  - Incident: #2726 image auto-bumped and consumer started at 18:50:36 UTC before chart gate landed.
  - Corrective #2730 default false merged 19:08 UTC.
  - stoa-infra #73 explicit chart gate=false merged 19:23 UTC; ArgoCD disabled consumer by ~19:38 UTC.

Day 1 — 2026-05-08 (DONE/PENDING):
  - #2734 replaced the reload-based regression test; main build succeeded.
  - #2733 PR-1A5 evidence pack merged 07:30 UTC: data-path PASS while enabled, caveat disabled at end of test window.
  - stoa-infra #75 A1b activation merged 07:40 UTC; read-only check shows prod env `ENABLE_AUDIT_TRAIL_CONSUMER="true"` and group `audit-trail-pg-consumer` Stable/lag 0.
  - PENDING: PR-1A6 evidence amend with `PR-1B_UNBLOCKED` verdict after manual non-chat mutation while consumer remains enabled.

Day 2:
  - If PR-1A6 evidence amend PASS: PR-1B can start.
  - If PR-1A6 evidence amend FAIL: keep PR-1B blocked and open corrective follow-up.

Day 3-5:
  - PR-1B audit log API + UI (~2 days).
  - PR-3 guardrails runtime truth (parallel after Annex B locked).

Day 6:
  - PR-4 nav IA cleanup.

Total: still roughly ~2 sprint weeks for the full chain. PR-2 already shipped; MEGA-A is now blocked only on PR-1A6 post-activation evidence before PR-1B.
```

# Annex A — Mini-spec: Audit Log API contract (PR-1B)

**Lock this annex before PR-1B starts**. Codex must conform to the shapes below; deviations require updating this annex first.

## Endpoints

```
GET  /v1/audit/{tenant_id}                # existing — list (no change)
GET  /v1/audit/{tenant_id}/stats          # NEW
GET  /v1/audit/{tenant_id}/actions        # NEW
GET  /v1/audit/{tenant_id}/export/csv     # existing
GET  /v1/audit/{tenant_id}/export/json    # existing
```

## Filters (must be supported on `list`, `stats`, both `export/*`)

| Param | Type | Notes |
|---|---|---|
| `start_date` | ISO 8601 datetime | UI envoie `start_date` (PAS `date_from`). PR-0 corrige le mapping cassé côté UI. |
| `end_date` | ISO 8601 datetime | Idem. |
| `action` | string | Match exact sur `audit_events.action`. |
| `status` | `success` \| `failure` \| `warning` \| `blocked` | |
| `resource_type` | string | If already supported by `list`, expose on `stats` too. |
| `search` | string | Free-text on path/resource. List only. |

## `GET /stats` response

```ts
{
  total_events: number,
  success_count: number,
  failed_count: number,
  unique_actors: number,
  by_action: Record<string, number>,   // top 20, sorted desc
  by_status: Record<string, number>,
  window_start: string,                 // ISO 8601
  window_end: string                    // ISO 8601
}
```

**Critical**: les KPIs UI (Total/Successful/Failed/Unique Actors) consomment `/stats`, plus jamais des calculs `entries.filter(...).length` côté client (cf. finding A3).

## `GET /actions` response

```ts
{
  actions: [
    { action: string, count: number }   // top 100, sorted desc, last 30 days
  ],
  window_start: string,
  window_end: string
}
```

UI populate le filter `<select>` avec `actions[]`. "All actions" reste premier.

## Actor resolution semantics

Chaque entrée retournée par `/list` contient désormais:

```ts
{
  // ... existing fields ...
  user_id: string | null,
  user_email: string | null,
  user_display_name: string | null,    // NEW — résolu via Keycloak admin API
  user_resolved: boolean               // NEW — false si Keycloak down/user not found
}
```

**Cache**: `cachetools.TTLCache(maxsize=2000, ttl=300)` côté API (Keycloak rate-limited).
**Fallback non-bloquant**: si Keycloak down, `user_resolved=false`, l'opération ne raise pas.

UI display priority: `user_email || user_display_name || user_id (badge "unresolved")`.

## Demo fallback semantics (AR-3)

Env var `STOA_AUDIT_DEMO_FALLBACK` :
- Default: `false` en prod (vérifier via startup log).
- Default: `true` en dev/test.
- Quand le fallback EST déclenché (env=true ET PG+OpenSearch indisponibles), la réponse contient `{"source": "demo", "warning": "Audit backend unavailable"}`. Jamais silencieux.

## Auto-refresh policy (AR-4)

Côté UI, exponential backoff sur erreur:
- Initial: 30s.
- Sur erreur HTTP: ×2, plafonné 300s. Séquence: 30s → 60s → 120s → 240s → 300s → 300s…
- Sur succès: reset à 30s.
- État UI: "Last refreshed Xs ago" (vert) ou "Refresh failed — retrying in Ns" (orange).

## Tests obligatoires (cf. PR-1B section)

- pytest: `test_stats_endpoint_returns_aggregates`, `test_actions_endpoint_returns_distinct`, `test_demo_fallback_disabled_when_env_false`, `test_resolve_actor_caches_keycloak_lookup`.
- vitest: stats consumption, actions consumption, actor unresolved badge, exponential backoff math, split-button export.

---

# Annex B — Mini-spec: Guardrails runtime state contract (PR-3)

**Lock this annex before PR-3 starts**. Bug racine actuel: `metrics?.guardrails?.pii_detections || 0` masque `null` en `0`. Cette annexe fixe les sémantiques pour empêcher la régression.

**PR-3A implementation contract**: `docs/plans/2026-05-10-guardrails-runtime-truth-contract.md` elaborates this annex for implementation. It does not change the validated AR-1/AR-2 decisions above.

## Endpoints

```
GET  /v1/admin/gateways/guardrails/config        # NEW
GET  /v1/admin/gateways/metrics                  # extend with freshness fields
GET  /v1/admin/gateways/metrics/guardrails/events?limit=N  # existing
```

## `GET /guardrails/config` response

```ts
{
  pii_enabled: boolean,
  injection_detection_enabled: boolean,
  prompt_guard_enabled: boolean,
  content_filter_enabled: boolean,
  rate_limit_enabled: boolean,
  opa_policy_enabled: boolean,
  source: "env" | "runtime" | "config-service",
  updated_at: string                   // ISO 8601
}
```

Source de vérité: probablement env vars du gateway Rust. Si endpoint admin gateway disponible (`/admin/config`), proxy via cp-api. Sinon lecture env côté cp-api avec doc claire ("source: env").

## Metrics response — freshness fields

Extension de `/v1/admin/gateways/metrics` (objet `guardrails`):

```ts
{
  guardrails: {
    pii_detections: number | null,
    injection_blocks: number | null,
    prompt_guard_blocks: number | null,
    content_filter_blocks: number | null,
    rate_limit_blocks: number | null,
    last_sample_at: string | null,        // ISO 8601
    metrics_age_seconds: number | null,
    source_healthy: boolean
  }
}
```

**Critical**: utiliser `null` pour "inconnu/pas de donnée", **JAMAIS** retourner `0` quand on ne sait pas. Le frontend distingue les états sur cette base.

## State semantics (UI rendering)

| Backend state | UI rendering per card |
|---|---|
| `enabled=false` | "Disabled" pill (gray), no count |
| `enabled=true`, `count=0`, `source_healthy=true`, recent `last_sample_at` | "0 events · last sample 12s ago" |
| `enabled=true`, `count>0`, `source_healthy=true` | normal count |
| `last_sample_at=null` | "No metrics sample" |
| `metrics_age_seconds > 60` | "Stale metrics · last sample 47m ago" (amber) |
| `source_healthy=false` | "Metrics unavailable" (red icon) |

**Anti-pattern explicite** à interdire dans la review:
```ts
metrics?.guardrails?.pii_detections || 0   // ❌ collapses null and 0
```
Pattern correct:
```ts
const count = metrics?.guardrails?.pii_detections;
if (count === null || count === undefined) return <NoData/>;
return <Count value={count} fresh={metrics.guardrails.metrics_age_seconds < 60}/>;
```

## Time range selector

Aligné sur Live Calls: `1h / 6h / 24h / 7d`. Propage à `/metrics` et `/metrics/guardrails/events`.

## IA decision (depends on AR-1)

Si AR-1 retient la recommandation (clarification, pas fusion):
- **Subtitle Security & Guardrails** (`/observability/security`): "Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring".
- **Subtitle Security Posture** (`/security-posture`): "Compliance findings, security score, configuration assessment".

Si AR-1 retient fusion: les deux pages deviennent une seule sous Observability, et PR-3 + PR-4 absorbent la fusion (effort ×2 — re-estimer).

## Tests obligatoires (cf. PR-3 section)

- pytest: `test_guardrails_config_endpoint`, `test_metrics_null_vs_zero` (assertion explicite que `null` n'est pas converti en `0`).
- vitest: 5 card states (healthy+0, healthy+N, disabled, stale, error), config panel real state, time range selector propagation.

---

# Required upfront work (before codex starts)

1. **You decide AR-1 → AR-6** (table top of doc) and fill `STATUS:` cells in section "Arbitrages requis".
2. **Lock Annex A** (Audit Log API) — confirm shapes, schedule any breaking change to existing `/list` consumers (`user_display_name`, `user_resolved` are additive — safe).
3. **Lock Annex B** (Guardrails runtime) — confirm source of truth for `/guardrails/config` (env vs runtime endpoint) before PR-3 starts.
4. **Allocate Linear MEGA tickets** (run `/decompose` on this plan or create manually).
5. **Confirm PR-0 scope is acceptable** (5 cosmetic fixes + 1 functional bug A4 in one chore PR).
6. **Confirm PR-1A access** (someone with prod OVH kubeconfig runs the investigation, or grant codex temporary access).
7. **Flip `validation_status: draft → validated`** in frontmatter once 1+2+3 done. PR-0 can start before 2/3 are locked (PR-0 doesn't touch contracts).

## Delivery closure — 2026-05-09

Status: DELIVERED

MEGA-A — Audit Log Data Integrity:
Delivered and runtime-verified.

MEGA-B — Runtime Observability Data Integrity:
Delivered and runtime-verified.

Final merged PR:
PR-4 nav IA cleanup — #2745, merged 2026-05-09 08:18 UTC.
