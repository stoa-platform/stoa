# Audit: Audit Trail DORA Compliance

**Date**: 2026-04-04
**Author**: Claude Opus 4.6 (automated) + Playwright E2E
**Ticket**: N/A (DORA compliance gap analysis)
**PR**: pending
**Duration**: ~3h

## Scope
Verify the Audit Log page works end-to-end: correct field mapping between API and UI, RBAC enforcement on export/security endpoints (viewer/devops get 403), and export button visibility per role.

## Results
**43 tests, 0 skipped, 0 failed** (16.2s E2E + unit tests)

### Coverage Matrix

| What was tested | How | Result |
|-----------------|-----|--------|
| Field mapping (user_email, client_ip, request_id) | vitest + Playwright | Pass |
| Date filter params (start_date/end_date) | vitest + Playwright | Pass |
| RBAC: viewer 403 on export/csv, export/json, security | pytest (8 tests) | Pass |
| RBAC: tenant-admin 200 on exports | pytest | Pass |
| Export button visible (cpi-admin, tenant-admin) | vitest | Pass |
| Export button hidden (devops, viewer) | vitest | Pass |
| Detail panel: JSON.stringify(details), IP, Request ID | Playwright | Pass |

### Dashboard/UI Verification

| Dashboard | Data Source | Real Data Visible | Evidence |
|-----------|-----------|-------------------|----------|
| Audit Log KPIs | PostgreSQL (demo fallback) | Total: 3, Successful: 2, Failed: 1 | trace in report |
| Audit Log Table | PostgreSQL (demo fallback) | 3 rows, bob@highfive.com | trace in report |
| Detail Panel | PostgreSQL (demo fallback) | JSON details, IP, Request ID | trace in report |
| Filter Panel | N/A (UI only) | Action, Status, Date pickers | trace in report |

## Bugs Found & Fixed

| # | Severity | Component | Issue | Fix |
|---|----------|-----------|-------|-----|
| 1 | P1 | control-plane-ui | Actor column empty — UI expected `actor`, API returns `user_email` | Aligned interface |
| 2 | P1 | control-plane-ui | Date filters ignored — UI sent `date_from`, API expects `start_date` | Fixed params |
| 3 | P1 | control-plane-api | viewer/devops can export PII (emails, IPs) | `require_role` added |
| 4 | P2 | control-plane-ui | Export button visible to viewer/devops | Conditional render |
| 5 | P2 | control-plane-ui | `entry.details` (object) rendered as React child → crash | `JSON.stringify` |
| 6 | P2 | control-plane-api | `global/summary` inline role check | `require_role(["cpi-admin"])` |
| 7 | P2 | keycloak | `tenant_id` missing from JWT | Protocol mapper added |

## Architecture Findings

- Dual-write audit trail (PG + OpenSearch) correctly wired via `AuditMiddleware`
- PG dual-write fires for mutations only (POST/PUT/PATCH/DELETE)
- Demo data fallback activates when both PG and OpenSearch return empty
- GDPR Art.17 erasure endpoint correctly pseudonymizes PII
- KC user attribute `tenant` needs explicit protocol mapper for JWT claim `tenant_id`

## Test File

**Path**: `e2e/tests/local-audit-trail.spec.ts`

```bash
cd e2e && npx playwright test tests/local-audit-trail.spec.ts --config playwright.local.config.ts
```

**Prerequisites**: Docker Compose stack + KC `tenant_id` mapper + `e2e/.env.local`

## Screenshots

Archived in `screenshots/`, captured during Playwright E2E run:

| File | What it proves |
|------|----------------|
| [`audit-01-login.png`](screenshots/audit-01-login.png) | Console login OK, Dashboard with 44.2K requests, tenant High Five |
| [`audit-02-page-loaded.png`](screenshots/audit-02-page-loaded.png) | Audit Log: 3 entries, `bob@highfive.com` in Actor column, Export button visible, KPIs (3/2/1), zero errors |
| [`audit-03-export.png`](screenshots/audit-03-export.png) | Row expand: Details JSON `{"demo": true}`, IP `192.168.1.101`, Request ID `req-00000001` |
| [`audit-04-filtered.png`](screenshots/audit-04-filtered.png) | Filter panel: Action/Status dropdowns, date range pickers, table visible |

Reproduce: `cd e2e && npx playwright test tests/local-audit-trail.spec.ts --config playwright.local.config.ts`
