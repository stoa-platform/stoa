---
id: plan-2026-05-07-observability-data-integrity
triggers: []                           # tactical remediation, no Decision Gate trigger
validation_status: draft               # upgrade to validated once arbitrages AR-1..AR-6 below are filled
challenge_ref: ""                      # not required (no triggers); add only if upgraded to challenged
---

# Plan — Observability Data Integrity

## Objectif

Restaurer la cohérence et la véracité des trois pages observability (`/observability/live-calls`, `/audit-log`, `/observability/security`) après la consolidation routes faite par codex (PR #2713 + #2715), qui a livré une façade propre devant des composants encore branchés sur des données incohérentes, vides, ou mockées.

**Source audit**: `docs/audits/2026-05-07-observability/AUDIT.md` (28 findings priorisés HIGH/MED/LOW).

## Scope

- **In**: 5 PRs séquencés données-d'abord (PR-0 quick wins, PR-1A/B audit log compliance, PR-2 live calls scope, PR-3 guardrails runtime, PR-4 nav IA).
- **Out**: pas de réécriture du pipeline OTel/Loki/Tempo/OpenSearch ; pas de migration schema `audit_events` ; pas de PII erasure UI ; pas de cross-tenant aggregation.

## Go / No-Go criteria

- **Go**: arbitrages AR-1..AR-6 ci-dessous remplis, PR-1A investigation accessible (kubeconfig prod OVH).
- **No-Go**: si l'investigation PR-1A révèle que le Kafka audit consumer n'existe pas en prod (réécriture infra requise hors scope).

---

## TL;DR

5 PRs, séquencés **données d'abord, polish ensuite**, regroupés en **2 MEGAs + 1 chore PR**:

| Order | PR | Type | MEGA | Priority | Blocked by |
|---|---|---|---|---|---|
| 1 | PR-0 | Chore (cosmetic + 1 functional) | None (standalone) | P0 (quick win) | — |
| 2 | PR-1A | Investigation (no code) | MEGA-A | P0 (compliance) | PR-0 merged |
| 3 | PR-1B | Audit Log API + UI | MEGA-A | P0 | PR-1A complete |
| 4 | PR-2 | Live Calls metric integrity | MEGA-B | P0 | PR-0 merged |
| 5 | PR-3 | Security & Guardrails runtime truth | MEGA-B | P1 | **Arbitrage IA** + PR-2 merged |
| 6 | PR-4 | Navigation IA cleanup | MEGA-B | P2 | **Arbitrage IA** + PR-3 merged |

**Total estimated**: ~50 pts across 2 MEGAs (sweet spot 21-34 each + 1 chore).

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
| **AR-1** | Security Posture (Governance) ↔ Security & Guardrails (Observability): fusion ou clarification IA stricte ? | PR-3, PR-4 | **Clarifier** — Posture = état/findings/score statique ; Guardrails = events runtime. Documenter sous-titres. Pas de fusion (personas distincts: compliance officer vs SRE). | STATUS: pending |
| **AR-2** | "Rate Limit" appartient à `/observability/security` ou `/observability/live-calls` ? | PR-3 | **Garder dans Security** (protection, pas signal de trafic). Corriger filter (S6) au lieu de retirer la carte. | STATUS: pending |
| **AR-3** | Demo data fallback côté audit API (`routers/audit.py:259 _init_demo_data()`): garder ou supprimer en prod ? | PR-1B | **Supprimer en prod**, garder en dev/test via env var `STOA_AUDIT_DEMO_FALLBACK=false` par défaut. | STATUS: pending |
| **AR-4** | Auto-refresh policy audit log: garder 30s polling fixe ou exponential backoff sur erreur ? | PR-1B | **Backoff exponentiel sur erreur** (30s → 60s → 120s → 300s plafonné), reset au prochain succès. Pas de refactor SWR (over-engineering). | STATUS: pending |
| **AR-5** | Fallback `'unknown'` dans `usePrometheus.ts:161 groupByLabel`: que faire quand un label est absent ? | PR-2 | **Renommer en `'(unlabelled)'`** + filtrer en aval, OU dropper la série. Le mot "unknown" est trompeur. | STATUS: pending |
| **AR-6** | Heatmap synthétique `CallFlowDashboard.tsx:336-361`: supprimer ou réécrire en vraie query ? | PR-2 | **Supprimer** (cacher derrière `<EmptyState>` "Heatmap unavailable"). Réécriture vraie = ticket séparé non-bloquant. | STATUS: pending |

**Note**: l'arbitrage est inline dans ce plan (pas un fichier séparé). Un nouveau commit met à jour `STATUS: <decision>` + flip `validation_status: validated` quand les 6 sont remplis. Codex lit ce frontmatter au début de chaque PR.

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
| PR-3 | **Yes** | New `/guardrails/config` endpoint + null/zero/stale/disabled/error semantics. Voir Annex B. |
| PR-4 | Partial | Wording IA dépend de AR-1; pas de nouvelle surface API. |

Une mini-spec doit fixer: shape request/response, sémantique d'état (null vs 0 vs disabled vs stale vs error), fallback behavior, acceptance criteria, tests obligatoires. Pas plus.

---

## MEGA-A — Audit Log Data Integrity

**Goal**: Garantir que `/audit-log` reflète la couverture DORA/NIS2 attendue (toutes les actions, pas seulement chat) et que l'UI ne ment pas sur l'état des données.

**Estimated**: 21 pts (3 phases)

**Binary DoD**:
- [ ] Production audit log retourne au moins une entrée non-`chat_*` après exercice manuel d'un emit path (ex: création API).
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

**Branch**: `feat/audit-log-coverage-and-ui`
**MEGA**: A — Phase 2
**Estimated**: 13 pts, ~400 LOC (backend + frontend + tests)
**Risk**: depends on PR-1A scope

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

# PR-2 — Live Calls Metric Integrity

**Branch**: `fix/live-calls-metric-scope`
**MEGA**: B — Phase 1
**Estimated**: 8 pts, ~250 LOC (frontend + ~50 LOC potential gateway)
**Risk**: medium (cross-stack: UI + Prometheus + possibly Rust)

## Goal

Aligner les scopes des queries Prometheus de Live Calls pour qu'aucune contradiction "KPI 39.3K vs No traffic" ne soit possible. Traiter `'unknown'` (fallback UI) explicitement. Supprimer la heatmap synthétique. Investiguer pourquoi certaines séries n'ont pas le label `path`.

## Findings addressed

L1, L2 (corrigé: cause = fallback UI + scrape), L3, L4, L5, L6, L8, L9, L10.

## In scope

### Investigation (étape 0, avant code)

1. **Identifier quelles séries `stoa_http_requests_total` existent en prod** et leur label set:
   ```bash
   curl -s 'https://api.gostoa.dev/v1/metrics/query?query={__name__="stoa_http_requests_total"}' \
     -H "Authorization: Bearer ${TOKEN}" | jq '.data.result[].metric'
   ```
   Output attendu: liste des séries (job=, path=, method=, status=).
2. **Identifier pourquoi certaines séries n'ont pas `path`**:
   - Hypothèse A: scrape config Prometheus drop le label.
   - Hypothèse B: une métrique tierce (NGINX, federation) exporte aussi `stoa_http_requests_total` sans `path`.
   - Hypothèse C: cp-api emet `stoa_control_plane_http_requests_total{endpoint=}` qui matche le pattern `stoa_http_requests_total` quand on requête sans préfixe (peu probable mais à vérifier).
3. **Vérifier**: si gateway emet bien le label `path` à 100% (test unitaire `metrics::record_http_request` est OK ; vérifier aussi en prod live).

Si l'investigation conclut que **toutes les séries ont `path`** mais que certaines valeurs sont vides (`""`), le fix est UI uniquement.
Si certaines séries n'ont **pas du tout** le label `path`, le fix est mixte: UI (filter pertinent) + Rust gateway (forcer label sur tous les paths) OU scrape config (ne pas drop).

### Frontend (`control-plane-ui/`)

1. Aligner le scope de **toutes** les queries de la page sur le même filtre `job`:
   ```promql
   stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}
   ```
   Ou décider explicitement qu'on inclut cp-api avec un label distinct.
   Cette décision conditionne les 7 queries du fichier (`CallFlowDashboard.tsx:142-227`).

2. **`'unknown'` handling** (`usePrometheus.ts:161` + UI):
   - Renommer le fallback `'unknown'` → `'(unlabelled)'` dans `groupByLabel` (cf. AR-5).
   - Dans `CallFlowDashboard.tsx`:
     - `topRoutes`: filtrer `(unlabelled)` si ≥1 vrai path présent. Sinon afficher `<EmptyState>` "Route labels are unavailable. Metrics report `path=\"\"` (empty). Check Prometheus scrape config or instrumentation."
     - `heatmap`: idem.

3. **Supprimer la heatmap synthétique** (`CallFlowDashboard.tsx:336-361`):
   - Supprimer le code `hash(s, n)` + `flatMap(...).Array.from({length:24}...)`.
   - Remplacer par un `<EmptyState>` "Heatmap unavailable until range-query data is wired." ou hide complete (cf. AR-6).
   - Ouvrir un ticket séparé "CAB-XXXX: implement real Live Calls traffic heatmap" non bloquant.

4. **KPI "Active Modes"** (l. 157-160, 584-590):
   - Soit corriger la query: `count(count by (job) (stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}))`.
   - Soit renommer le label en "Tracked Routes" et garder `count by (path)`.
   - Recommandation: corriger la query (Active Modes est l'intention produit).

5. **Bannière "scope mismatch"**:
   - Ajouter un calcul: `if totalRequestsVal > 0 && (edgeMcpTrend + sidecarTrend + connectTrend) === 0`, afficher une bannière jaune "Total requests counted, but no per-mode traffic. Possible scope mismatch — gateway scrape may not match expected job names."
   - Test régressif obligatoire (cf. point 8 user message).

6. **Trace contradiction** (L4):
   - Quand `/v1/monitoring/transactions` retourne empty mais Prometheus retourne >0, afficher "Request metrics are available, but no traces were found for this time range. Metrics source: Prometheus. Trace source: Tempo/OpenSearch pipeline."
   - Code site: l. 681-689 (LiveTraces empty message).

7. **Header duplication** (L8): vérifier au dev server qu'aucun layout parent injecte un second h1/subtitle. Si oui, retirer celui qui est en double dans le composant.

8. **Refresh button vs auto-refresh toggle** (L9): retirer le bouton Refresh, garder le toggle. Ou inverser. Décision esthétique secondaire — au choix de codex.

### Gateway (Rust, conditionnel sur investigation)

Si l'investigation montre que le gateway lui-même produit des séries sans label `path`:
- Vérifier `stoa-gateway/src/lib.rs:705-709` et `metrics.rs:1230-1238`.
- Le test `test_record_http_request` (`metrics.rs:1454`) prouve que `record_http_request` met bien les 3 labels — donc le bug serait ailleurs (scrape config?).
- Si trivial: fix dans la même PR.
- Sinon: ouvrir CAB séparé "Gateway Prometheus path label missing on production scrape" et le PR-2 se contente du UI.

## Out of scope

- Pas de réécriture vraie de la heatmap (ticket séparé).
- Pas de Tempo wiring (déjà en non-goal de PR #2713).
- Pas de modification du sélecteur de service (Gateway/Link/Connect) ni du filter logique.

## Codex prompt

```
You are working on STOA control-plane-ui (React 18, TS, Vite) with optional surface in stoa-gateway (Rust).

Context: PR #2713 consolidated /observability routes but the Live Calls page (/observability/live-calls) presents inconsistent data. KPI "Total Requests (1h)" shows 39.3K but per-mode breakdowns show "No traffic". "Top Routes" and "Traffic Heatmap" only show "unknown" (a UI fallback fabricated by groupByLabel in src/hooks/usePrometheus.ts:161). The heatmap is synthetic, generated from a deterministic hash on top routes (CallFlowDashboard.tsx:336-361).

Step 0 — Investigation (REQUIRED before code changes):

Run these PromQL queries against api.gostoa.dev (use a real Bearer token from a logged-in CPI Admin session — see docs/audits/2026-05-07-observability/AUDIT.md for context):

1. Inventory series:
   query={__name__="stoa_http_requests_total"}

2. Inventory histogram series:
   query={__name__="stoa_http_request_duration_seconds_bucket"}

3. Distinct job labels:
   query=count by (job) (stoa_http_requests_total)

4. Distinct path values:
   query=count by (path) (stoa_http_requests_total)

5. Series with empty/missing path:
   query=count(stoa_http_requests_total{path=""}) or count(stoa_http_requests_total) - count(stoa_http_requests_total{path!=""})

Document findings in docs/audits/2026-05-08-live-calls-investigation/promql-evidence.md before writing code.

Decision tree based on evidence:
- If all series have job ∈ {stoa-gateway, stoa-link, stoa-connect}: filter is correct, fix the missing-path issue only.
- If some series have other job values (e.g. stoa-control-plane-api): scope ambiguity — either filter them out or handle them as a separate stack.
- If some series have NO path label at all: that's the root cause of "unknown". Fix either Rust gateway emission or Prometheus scrape config.

Step 1 — Frontend changes (control-plane-ui/src/):

1. src/hooks/usePrometheus.ts:161
   Change `const key = r.metric[label] || 'unknown';` to `const key = r.metric[label] ?? '(unlabelled)';`
   Ensure consumers of groupByLabel handle the '(unlabelled)' key explicitly.

2. src/pages/CallFlow/CallFlowDashboard.tsx
   Define MODE_FILTER constant at top of file:
     const MODE_FILTER = 'job=~"stoa-gateway|stoa-link|stoa-connect"';
   Apply this filter to ALL stoa_http_requests_total and stoa_http_request_duration_seconds_bucket queries (lines 142-206).
   Verify totalRequests, totalErrors, p50/p99, activeModes, latencyBuckets, errorsByStatus, topRoutesP95, topRoutesCalls all use the same scope.

3. CallFlowDashboard.tsx:157-160 (activeModes query)
   Change to: count(count by (job) (stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}))
   Update subtitle from "Deployment modes" to whatever now matches reality.

4. CallFlowDashboard.tsx:321-333 (topRoutes parsing)
   Filter out '(unlabelled)' key from p95Map before sorting.
   If after filtering the resulting array is empty AND p95Map originally had only '(unlabelled)' key, render the EmptyState described below in the TopRoutes component.

5. control-plane-ui/src/pages/CallFlow/components/TopRoutes.tsx
   Add an empty state for the case "all routes are unlabelled":
   "Route labels unavailable. Metrics currently report missing or empty 'path' label. Check Prometheus scrape config and gateway instrumentation."
   Use the existing EmptyState component from @stoa/shared/components/EmptyState.

6. CallFlowDashboard.tsx:336-361 (heatmap synthesis)
   Delete this entire block (the hash() function and the flatMap distribution).
   Replace heatmapCells with empty state cards.tsx:644-655 — wrap TrafficHeatmap in a conditional that renders EmptyState "Heatmap unavailable. Real range-query implementation tracked in CAB-XXXX." when no real data is wired.
   Open a ticket placeholder comment: // TODO(CAB-XXXX): implement real heatmap via query_range over selected window

7. CallFlowDashboard.tsx — add scope-mismatch banner.
   After loading totalRequestsVal, edgeMcpTrend, sidecarTrend, connectTrend:
     const sumPerMode = (edgeMcpTrend.data?.[edgeMcpTrend.data.length-1]?.value ?? 0)
                      + (sidecarTrend.data?.[sidecarTrend.data.length-1]?.value ?? 0)
                      + (connectTrend.data?.[connectTrend.data.length-1]?.value ?? 0);
     const scopeMismatch = totalRequestsVal !== null && totalRequestsVal > 0 && sumPerMode === 0;
   If scopeMismatch, render an amber banner above the KPIs:
     "Total requests counted, but no per-mode traffic for the selected window. Some scraped series may not match expected job names. See <link to runbook>."

8. CallFlowDashboard.tsx:681-689 (LiveTraces empty message)
   When traces.length === 0 AND totalRequestsVal > 0, change emptyMessage to:
     "Request metrics are available, but no traces were found for this time range. Metrics source: Prometheus. Trace source: Tempo/OpenSearch pipeline."

9. CallFlowDashboard.tsx:440 verify <h1>Live Calls</h1> (already changed in PR-0).
   Investigate any duplicate header injected by parent layout — if found, remove the duplicate (one canonical title per page).

Step 2 — Gateway changes (CONDITIONAL on Step 0 evidence):

If evidence shows the Rust gateway emits series WITHOUT a path label (e.g. only on certain code paths), AND the fix is trivial (≤30 LOC):
  - Update stoa-gateway/src/lib.rs to ensure record_http_request is called on every response path.
  - Add a regression cargo test asserting the label is always set.

Otherwise:
  - Open a separate ticket "Gateway Prometheus path label missing — scrape or emission fix" and reference it in PR-2 description.
  - PR-2 is UI-only.

Tests required:

Frontend:
- src/__tests__/regression/live-calls-scope-mismatch.test.tsx — given total > 0 and per-mode = 0, assert banner is rendered.
- src/__tests__/regression/live-calls-unlabelled-routes.test.tsx — given groupByLabel returns {'(unlabelled)': 5000}, assert the EmptyState is rendered, NOT a Top Routes table with one row.
- src/pages/CallFlow/components/TopRoutes.test.tsx — empty state when all routes unlabelled.
- src/__tests__/regression/live-calls-no-synthetic-heatmap.test.tsx — assert heatmapCells is empty (no fake distribution).
- src/hooks/usePrometheus.test.ts — groupByLabel returns '(unlabelled)' not 'unknown' for missing label.

Backend (if gateway fix included):
- cargo test --package stoa-gateway --lib record_http_request_always_has_path_label

Acceptance criteria:
- [ ] All Prometheus queries on Live Calls use the same MODE_FILTER scope.
- [ ] No '(unlabelled)' route appears as a normal entry in Top Routes when other routes exist.
- [ ] When 100% of routes are unlabelled, an EmptyState is rendered, not a fake top route.
- [ ] Heatmap is empty/hidden until real data is wired.
- [ ] Scope-mismatch banner appears when KPI total > 0 but breakdowns are 0.
- [ ] Active Modes label matches what is actually counted.
- [ ] Tests added for all 5 regression scenarios.

Out of scope:
- Real heatmap implementation (separate ticket).
- Tempo / Loki / OpenSearch pipeline rewiring.
- Sidebar nav cleanup (PR-4).
- Demo data fallback (no demo data in this page; ensure code review confirms).

Commit message: fix(ui,gateway?): live calls metric scope alignment + unlabelled route handling (CAB-XXXX)
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

PRECONDITION: read docs/plans/2026-05-07-observability-data-integrity.md (section 'Arbitrages requis'). If AR-1 (Security Posture vs Security & Guardrails) is not yet decided, STOP and request decision before proceeding.

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

```
[Standalone chore]
└── PR-0 — Observability quick wins (1pt) — CAB-XXXX

[MEGA-A: Audit Log Data Integrity] (21pt, 3 phases)
├── Phase 1 — PR-1A Investigation (3pt) — CAB-XXXX
├── Phase 2 — PR-1B API + UI (13pt) — CAB-XXXX
└── Phase 3 — PR-1C Tests + evidence (5pt) — CAB-XXXX [optional, can fold into 1B]

[MEGA-B: Runtime Observability Data Integrity] (21pt, 3 phases)
├── Phase 1 — PR-2 Live Calls metric integrity (8pt) — CAB-XXXX
├── Phase 2 — PR-3 Security & Guardrails runtime truth (8pt, BLOCKED on AR-1) — CAB-XXXX
└── Phase 3 — PR-4 Sidebar IA cleanup (5pt, BLOCKED on AR-1+PR-3) — CAB-XXXX
```

# Sequencing (real timeline)

```
Day 0 (today):
  - Resolve AR-1 to AR-6 (1h max, fill `STATUS:` cells in section "Arbitrages requis" of this plan, then flip `validation_status: validated`).

Day 0-1:
  - PR-0 quick wins: open, review, merge (~2h end-to-end).

Day 1-2:
  - PR-1A investigation: requires prod kubectl access (~half day).

Day 2-4:
  - PR-1B audit log + UI (in parallel with PR-2 if 2 dev capacity).
  - PR-2 live calls metric integrity (parallel).

Day 5-6:
  - PR-3 security guardrails runtime (after AR-1 resolved).

Day 7:
  - PR-4 nav cleanup.

Total: ~1 sprint week if focused, ~2 weeks if shared with other work.
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
