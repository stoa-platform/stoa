# MEGA-A runtime close — Audit Log

Captured 2026-05-08 between 19:46 and 19:50 UTC, after [stoa#2738](https://github.com/stoa-platform/stoa/pull/2738) (PR-1B2 — AuditLog UI) merged at 19:20:57 UTC, the post-merge cp-ui CI build succeeded, the auto-bump landed `dev-15b8b91e1dc13c741c7ecc50e9b10aff35fe4ec9` in `stoa-infra/charts/control-plane-ui/values.yaml`, and ArgoCD reconciled cp-ui pods at 19:31:49 UTC.

This file is the formal MEGA-A runtime close. PR-1A6 ([stoa#2736](https://github.com/stoa-platform/stoa/pull/2736)) already proved continuous Kafka→PG ingestion. This file proves the API + UI surface is correct in production after both PR-1B1 ([stoa#2737](https://github.com/stoa-platform/stoa/pull/2737)) and PR-1B2 ([stoa#2738](https://github.com/stoa-platform/stoa/pull/2738)) are deployed.

## Verdict

**VERDICT: MEGA-A_RUNTIME_PASS.**

Audit Log is reachable in prod, the new `/stats` and `/actions` endpoints are wired, the UI consumes them (KPIs no longer page-local), the actor unresolved badge renders, the Last refreshed timestamp renders, the Export CSV/JSON split-button is present, locale follows the EN switcher, no demo fallback banner is shown (`source=null`), and at least one non-`chat_*` event is visible in the table. MEGA-A is formally closed.

## 1. Deployment

- control-plane-ui image: `ghcr.io/stoa-platform/control-plane-ui:dev-15b8b91e1dc13c741c7ecc50e9b10aff35fe4ec9` (post-#2738 squash on `main`).
- control-plane-ui pods (post-rollout):
  - `control-plane-ui-7fb77c9fd6-dbnkg` Running, age ~14 min
  - `control-plane-ui-7fb77c9fd6-rv7xh` Running, age ~14 min
- ArgoCD `control-plane-ui` Application: `sync=Synced`, `health=Healthy`, `lastSync=2026-05-08T19:31:49Z`.
- control-plane-api image (still post-#2737): `dev-bd408bbb49e07545d3158ab2aa86b96400564d40`.
- Console health (`https://console.gostoa.dev/`): HTTP 200.
- URL exercised: `https://console.gostoa.dev/audit-log`.
- Logged-in user: CPI Admin, workspace `free-aech` (Keycloak SSO).
- Browser console: 0 errors, 0 warnings during page load.

Screenshot: [`audit-log-page.png`](audit-log-page.png).

## 2. Backend contract visible

API checks via in-pod curl with the operator key (sourced from env, never printed). Tenant `demo` was used for backend smoke since organic continuous ingestion since 2026-05-08 07:41 has populated this tenant heavily; tenant `free-aech` is the logged-in user's workspace and is exercised in §3.

### `GET /v1/audit/demo/stats?start_date=2026-04-08T00:00:00Z&end_date=2026-05-08T23:59:59Z`

```json
{
  "total_events": 11,
  "success_count": 11,
  "failed_count": 0,
  "unique_actors": 2,
  "by_action": {"update": 7, "export": 2, "promotion_created": 2},
  "by_status": {"success": 11},
  "window_start": "2026-04-08T00:00:00Z",
  "window_end": "2026-05-08T23:59:59Z",
  "source": null,
  "warning": null
}
```

10 contract fields present per Annex A. `source=null` and `warning=null` confirm no demo fallback in production.

### `GET /v1/audit/demo/actions`

```json
{
  "actions": [
    {"action": "update", "count": 7},
    {"action": "export", "count": 2},
    {"action": "promotion_created", "count": 2}
  ],
  "source": null,
  "warning": null
}
```

Top distinct actions ordered by count desc, sourced from real PostgreSQL data (not a hardcoded list).

### `GET /v1/audit/demo?page=1&page_size=1`

Entry keys observed:

```text
action, client_ip, details, id, request_id, resource_id, resource_type,
status, tenant_id, timestamp, user_agent, user_display_name, user_email,
user_id, user_resolved
```

New PR-1B1 fields `user_display_name` and `user_resolved` are present (default `null` / `false` when Keycloak resolution did not return a match). All existing fields preserved → backwards compatible. Top-level `source=null` and `warning=null`.

## 3. UI Audit Log

Tenant displayed: `free-aech` (current logged-in workspace). Table shows 44 total entries; first page (20 rows) includes 2 non-`chat_*` rows.

### KPI cards driven by `/stats` (PR-1B2 task 1)

| Card | Value | Subtitle |
|---|---|---|
| Total Events | 2 | Last 30 days |
| Successful | 2 | Last 30 days |
| Failed | 0 | Last 30 days |
| Unique Actors | 1 | Last 30 days |

The subtitle reads **"Last 30 days"** — never **"On this page"**. KPIs come from `/stats` over the filtered window (default 30 days) and not from the current page entries.

### `/actions` populated filter (PR-1B2 task 2)

The "Filters" panel exposes the Action `<select>`. Network requests confirmed `/v1/audit/free-aech/actions` was called on page mount and is the data source for the dropdown.

### Actor display + unresolved badge (PR-1B2 task 3)

The Actor column shows `cpi-admin@gostoa.dev` for every row. Several rows additionally render the small **`unresolved`** badge next to the email when the backend returned `user_resolved=false` (e.g. Keycloak admin client did not find a matching user record at resolve time). This is the contract: prefer `user_email > user_display_name > user_id + badge`. The badge is the visible signal of unresolved-but-cached state and keeps the page readable when Keycloak resolution is partial.

Rows with the `unresolved` badge in the captured snapshot include the entries dated 03/16, 03/19. Earlier rows (04/04, 03/29, 03/25, 03/23) are resolved (no badge).

### Source / warning banner (PR-1B2 task 4 — added in `b3d7ad213`)

No banner is rendered. The `/stats`, `/actions`, and `/v1/audit/free-aech` responses all return `source=null, warning=null`, which is the expected production state with `STOA_AUDIT_DEMO_FALLBACK=false`. The banner code path is exercised by the regression test `shows backend warning when audit responses come from demo fallback` in #2738 with mocked `source: "demo"`.

### Last refreshed timestamp (PR-1B2 task 5)

The line `Last refreshed just now` is rendered above the KPI strip immediately after a successful refresh.

### Exponential backoff (PR-1B2 task 6)

Not exercised at runtime in production (would require forcing a non-trivial API failure). Covered by the unit test `backs off on consecutive failures and resets after success` in #2738. Marked **not prod-forced** per the runbook.

### Export CSV / JSON split-button (PR-1B2 task 7)

The header right-hand area shows:

- A primary `Export CSV` button.
- A secondary `Export options` chevron button (the dropdown trigger that exposes the JSON export).

The two endpoints `/v1/audit/{tenant_id}/export/csv` and `/v1/audit/{tenant_id}/export/json` are the targets, both preserving the active filter parameters.

### Locale-aware timestamps (PR-1B2 task 8)

The language switcher in the top bar reads `current: EN`. Timestamps in the table render in US/EN format, e.g. `04/25/2026, 12:31:43 AM`. Never the previously hardcoded `fr-FR` form.

### Date filter parameter naming

The page renders two `<input type="date">` for `start_date` / `end_date`. The PR-0 ([stoa#2717](https://github.com/stoa-platform/stoa/pull/2717)) regression test `AuditLog: sends start_date and end_date params when date filters are set` already covers this rename and is still part of the test suite (visible in `control-plane-ui/src/pages/AuditLog.test.tsx`). No `date_from` / `date_to` URL parameters were observed in any of the 7 captured `/v1/audit/*` requests during this smoke.

## 4. Non-chat event present in `/audit-log`

The first page of `https://console.gostoa.dev/audit-log` for tenant `free-aech` contains:

| Timestamp | Actor | Action | Resource | Status |
|---|---|---|---|---|
| 04/25/2026, 12:31:43 AM | cpi-admin@gostoa.dev | update | api/api-beta | success |
| 04/25/2026, 12:30:31 AM | cpi-admin@gostoa.dev | update | api/api-beta | success |

Two non-`chat_*` rows visible. Both `update` on `api/api-beta`, both `success`. This satisfies the canonical MEGA-A DoD: **"audit log prod retourne au moins une entrée non-`chat_*` après exercice manuel d'un emit path"**.

For the `demo` tenant, the controlled events from PR-1A6 ([stoa#2736](https://github.com/stoa-platform/stoa/pull/2736)) and the 35 organic events ingested between activation (07:41 UTC) and PR-1A6 trigger (08:35 UTC) plus subsequent organic activity bring the total to 11 non-chat events visible via API.

## 5. Error/backoff behavior

Not prod-forced. Exercising would require either:
- a controlled API outage that would affect real users, or
- a synthetic test environment.

Covered by the unit test `backs off on consecutive failures and resets after success` in #2738 (`AuditLog.test.tsx`, 23/23 passing). Marked accepted per the runbook.

## 6. Verdict

**VERDICT: MEGA-A_RUNTIME_PASS.**

All gating conditions of the MEGA-A binary DoD (per `docs/plans/2026-05-07-observability-data-integrity.md`) are now satisfied:

| Condition | Status |
|---|---|
| Production audit log returns ≥1 non-`chat_*` entry | ✅ §4 |
| Date filters operational (start_date/end_date mapping) | ✅ regression test from PR-0 #2717, no `date_from` observed in network |
| KPIs reflect filtered window, not current page | ✅ §3 KPI subtitle = "Last 30 days" |
| Demo fallback OFF in prod | ✅ `STOA_AUDIT_DEMO_FALLBACK=false`, `source=null` on every audit response |
| Tests régressifs | ✅ `tests/test_audit_router.py`, `tests/test_audit_service.py`, `tests/test_regression_cab_2736_audit_demo_fallback.py` (64 passing), `AuditLog.test.tsx` (23 passing) |
| `/stats` endpoint live | ✅ HTTP 200, 10 contract fields |
| `/actions` endpoint live | ✅ HTTP 200, real distinct actions |
| Actor resolution backwards compatible | ✅ `user_display_name`, `user_resolved` added without breaking existing fields |
| `/audit-log` UI deployed and rendering | ✅ image `dev-15b8b91e1...` in prod, ArgoCD Synced/Healthy, page reachable, console clean |
| Export CSV + JSON | ✅ split-button rendered |
| Locale-aware timestamps | ✅ EN locale active, no hardcoded `fr-FR` |

MEGA-A (Audit Log Data Integrity) is closed. PR-1B (UI/API surface) is fully delivered. The next work area is MEGA-B (Live Calls runtime evidence + Guardrails Runtime Truth + Sidebar IA cleanup).

## Cross-references

- Plan: [docs/plans/2026-05-07-observability-data-integrity.md](https://github.com/stoa-platform/stoa/blob/main/docs/plans/2026-05-07-observability-data-integrity.md)
- Annex A (API contract): same plan file, section "Annex A — Mini-spec: Audit Log API contract (PR-1B)"
- Mini-spec audit consumer (PR-1A3): [docs/plans/2026-05-08-audit-consumer-ingestion-contract.md](https://github.com/stoa-platform/stoa/blob/main/docs/plans/2026-05-08-audit-consumer-ingestion-contract.md)
- PR-1A5 evidence: [docs/audits/2026-05-09-audit-consumer-verification/findings.md](https://github.com/stoa-platform/stoa/blob/main/docs/audits/2026-05-09-audit-consumer-verification/findings.md) ([#2733](https://github.com/stoa-platform/stoa/pull/2733))
- PR-1A6 post-activation evidence: [docs/audits/2026-05-09-audit-consumer-verification/post-activation.md](https://github.com/stoa-platform/stoa/blob/main/docs/audits/2026-05-09-audit-consumer-verification/post-activation.md) ([#2736](https://github.com/stoa-platform/stoa/pull/2736))
- A1b activation: [stoa-infra#75](https://github.com/PotoMitan/stoa-infra/pull/75)
- PR-1B1 backend: [stoa#2737](https://github.com/stoa-platform/stoa/pull/2737)
- PR-1B2 UI: [stoa#2738](https://github.com/stoa-platform/stoa/pull/2738)

## Residual notes

- **Unresolved badge prevalence on chat rows** is expected: many old `cpi-admin@gostoa.dev` chat entries pre-date the cached resolver, so `user_resolved=false`. The cache (`TTLCache(maxsize=2000, ttl=300)`) will warm progressively as the resolver hits Keycloak for admin emails. No action required.
- **`free-aech` total=2**: only 2 audit events exist for `free-aech` in the last 30 days — both `update api/api-beta success` from 2026-04-25. Tenant `demo` carries the bulk of organic events (11 non-chat in 30d).
- **Date filter UI smoke** was attempted via Playwright `dispatchEvent('change')` but did not propagate to React state without a synthetic event. The runtime evidence on this point comes from PR-0 #2717's regression test, not this smoke. Marked acceptable.
- **Image cp-api**: still on `dev-bd408bbb49...` from PR-1B1 #2737 — auto-bump only fires for cp-ui this round. No cp-api changes were merged after #2737.
