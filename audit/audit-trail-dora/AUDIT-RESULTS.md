# Audit Trail DORA Compliance — Audit Results

**Date**: 2026-04-04
**Environment**: Docker Compose local stack (Keycloak 26.5.3 + Control Plane API + Console)
**Auditor**: Claude Opus 4.6 (automated) + Playwright (E2E verification)
**Ticket**: Audit Trail RBAC tightening + field mapping fix

## Final Score: 41/41 tests pass + 2/2 E2E pass

| Layer | Framework | Tests | Result |
|-------|-----------|-------|--------|
| API RBAC | pytest | 28 | 28/28 pass |
| UI Components | vitest | 13 | 13/13 pass |
| E2E Playwright | Playwright local | 2 | 2/2 pass (16.2s) |
| **Total** | | **43** | **43/43 pass** |

## Changes Verified

### 1. Field Mapping Fix (UI)
**Before**: UI interface expected `actor`/`actor_type`/`ip_address` — columns were empty.
**After**: UI maps `user_email`/`user_id`/`client_ip`/`request_id` from API response.

| API Field | UI Display | Screenshot Proof |
|-----------|-----------|-----------------|
| `user_email: bob@highfive.com` | Actor column: `bob@highfive.com` | `audit-02-page-loaded.png` |
| `client_ip: 192.168.1.101` | Detail panel: IP ADDRESS `192.168.1.101` | `audit-03-export.png` |
| `request_id: req-00000001` | Detail panel: REQUEST ID `req-00000001` | `audit-03-export.png` |
| `details: {"demo": true}` | Detail panel: `{ "demo": true, "index": 1 }` | `audit-03-export.png` |

### 2. Date Filter Fix
**Before**: UI sent `date_from`/`date_to`, API expected `start_date`/`end_date` — filters silently ignored.
**After**: Params aligned. Filter panel visible in `audit-04-filtered.png`.

### 3. RBAC Tightening (API)
**Before**: All roles (viewer, devops) could export PII and view security events.
**After**: Exports and security events restricted to `cpi-admin` + `tenant-admin`.

| Endpoint | viewer | devops | tenant-admin | cpi-admin |
|----------|--------|--------|-------------|-----------|
| `GET /audit/{tenant}` | 200 | 200 | 200 | 200 |
| `GET /audit/{tenant}/export/csv` | **403** | **403** | 200 | 200 |
| `GET /audit/{tenant}/export/json` | **403** | **403** | 200 | 200 |
| `GET /audit/{tenant}/security` | **403** | **403** | 200 | 200 |
| `GET /audit/global/summary` | 403 | 403 | 403 | 200 |

### 4. Export Button Hidden (UI)
**Before**: All roles saw the Export button.
**After**: Only `cpi-admin` and `tenant-admin` see Export. Verified via vitest persona tests.

## Screenshots Archive

| File | What it proves |
|------|----------------|
| `audit-01-login.png` | Console login as parzival (tenant-admin, High Five), dashboard with metrics |
| `audit-02-page-loaded.png` | Audit Log page: 3 entries, KPI cards, `bob@highfive.com` in Actor column, Export button visible, zero errors |
| `audit-03-export.png` | Row expand: Details JSON, IP Address `192.168.1.101`, Request ID `req-00000001` |
| `audit-04-filtered.png` | Filter panel open (Action, Status, date range pickers), table visible |

## Traces & Video

| File | Duration | What it captures |
|------|----------|-----------------|
| `trace-tenant-admin.zip` | 14.4s | Full login + audit page + row expand + export + filters |
| `trace-viewer-rbac.zip` | 65ms | API-level RBAC verification (viewer token) |
| `video-tenant-admin.webm` | 14.4s | Screen recording of tenant-admin test flow |

View traces: `npx playwright show-trace audit/audit-trail-dora/trace-tenant-admin.zip`

## Keycloak Configuration

Protocol mapper `tenant_id` added to `control-plane-ui` client:
- User attribute `tenant` mapped to JWT claim `tenant_id`
- Required for `@require_tenant_access` decorator to work

## Deliverables

### Code
- `control-plane-ui/src/pages/AuditLog.tsx` — Field mapping + filter params + conditional Export
- `control-plane-api/src/routers/audit.py` — `require_role` on exports/security/summary

### Tests
- `control-plane-api/tests/test_audit_router.py` — +8 RBAC tests (viewer/devops 403)
- `control-plane-ui/src/pages/AuditLog.test.tsx` — +7 tests (export visibility + field mapping)
- `e2e/tests/local-audit-trail.spec.ts` — 2 E2E scenarios with screenshots

### Documentation
- `docs/runbooks/audit-trail-query.md` — SQL + API queries for incident investigation

## Known Limitations

| Gap | Status | Mitigation |
|-----|--------|------------|
| Keycloak login events not in audit trail | Open | Check KC Admin Console > Events |
| Gateway data plane logs separate | Open | `kubectl logs` on stoa-gateway pods |
| PG dual-write only for mutations | By design | OpenSearch captures GET requests |
| Viewer E2E not tested in Playwright | Skip | No `aech` user in local KC. Covered by 28 pytest |
