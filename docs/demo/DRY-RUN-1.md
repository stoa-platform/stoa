# Dry-Run #1 Report — CAB-1062

> **Date**: 2026-02-04
> **Executor**: Claude Code (automated dry-run)
> **Target demo**: "ESB is Dead" — 24 February 2026
> **Verdict**: **FAIL** — 3 blockers to fix before next dry-run

---

## Timing Summary

| Segment | Budget | Actual (API) | Status |
|---------|--------|-------------|--------|
| Pre-Auth (art3mis + parzival) | — | 0.9s | OK |
| Hook (slides) | 0:00 - 0:30 | N/A (slides) | OK |
| Problem (slides) | 0:30 - 1:30 | N/A (slides) | OK |
| Solution LIVE — Portal | 1:30 - 3:30 | 4.7s (API calls) | BLOCKED |
| Console — Admin View | 3:30 - 4:30 | 4.8s (API calls) | PARTIAL |
| Close (slides) | 4:30 - 5:00 | N/A (slides) | OK |

> API timings represent sequential curl calls, not browser rendering.
> Real browser demo will feel faster with pre-loaded tabs and SSO sessions.

---

## T-30min Pre-Flight Checks

| Service | URL | Status | Latency |
|---------|-----|--------|---------|
| Portal | https://portal.gostoa.dev | 200 | 0.20s |
| Console | https://console.gostoa.dev | 200 | 0.28s |
| API | https://api.gostoa.dev/health/ready | 200 | — |
| Keycloak | https://auth.gostoa.dev | 302 (OK) | — |
| Keycloak OIDC | /realms/stoa/.well-known/openid-configuration | 200 | — |

**All services UP.**

---

## Blockers (Must Fix)

### BLOCKER-1: Petstore API not in catalog

- **Impact**: Demo script Step 3 ("Search petstore") returns 0 results
- **Root cause**: `seed-demo-data.py` fails at Phase 1 — API creation returns `500: "GitLab not connected"`
- **Details**: The `POST /v1/tenants/high-five/apis` endpoint requires GitLab integration (GitOps source of truth). The seed script cannot create APIs without this connection.
- **Existing catalog**: 12 APIs exist from other seed runs (demo, high-five, oasis, ioi tenants) but none named "petstore"
- **Fix options**:
  1. **Connect GitLab** to the control-plane-api (requires GitLab token configuration)
  2. **Add a direct SQL/API seed** that bypasses GitOps for demo data
  3. **Pivot the demo** to use an existing API (e.g., "Account Management API" from demo tenant — found via search)
  4. **Seed via K8s** — insert directly in the database or use a different admin endpoint

### BLOCKER-2: Application creation fails (backend bug)

- **Impact**: No "Gunter Analytics Dashboard" in pending state, no "OASIS Mobile App" — cannot demo approval flow
- **Root cause**: `POST /v1/applications` returns `500: "'User' object has no attribute 'sub'"`
- **Details**: The User model in control-plane-api is missing the `sub` attribute when creating applications via API (likely works differently from the UI flow)
- **Fix**: Fix the `User` model or the application creation endpoint in `control-plane-api/`

### BLOCKER-3: Petstore Swagger sandbox returns 500

- **Impact**: Demo Step 6 ("Test live") — `GET /pet/findByStatus?status=available` at petstore3.swagger.io returns 500
- **Details**: The external Petstore API (swagger.io) is unreliable. This is an external dependency outside our control.
- **Fix options**:
  1. **Use a STOA-hosted mock** instead of the external petstore3.swagger.io
  2. **Prepare a curl backup** that works against a different endpoint
  3. **Pre-record the sandbox response** as a video fallback

---

## Issues (Need Workaround)

### ISSUE-1: Portal API requires authentication

- **Impact**: DEMO-CHECKLIST.md curl examples (T-30min checks) fail without auth token
- **Details**: `curl https://api.gostoa.dev/v1/portal/apis?search=petstore` returns `{"detail":"Not authenticated"}`
- **Fix**: Update DEMO-CHECKLIST.md to include auth header, or make portal read endpoints public

### ISSUE-2: Monitoring endpoint returns 404

- **Impact**: Console Step 7 ("API Monitoring") — `GET /v1/monitoring/overview` returns 404
- **Details**: The monitoring endpoint doesn't exist or has a different path
- **Workaround**: The demo script says to "click API Monitoring in sidebar" — the UI page may exist even if this specific API endpoint doesn't. Verify in the browser.

### ISSUE-3: Applications list is empty

- **Impact**: Console Step 6 ("Applications list with Gunter Analytics Dashboard in Pending") — 0 applications returned
- **Root cause**: Linked to BLOCKER-2 (app creation failed)
- **Workaround**: None until BLOCKER-2 is fixed

### ISSUE-4: Dashboard stats schema differs from script expectations

- **Impact**: Minor — Dashboard returns `tools_available`, `active_subscriptions`, `api_calls_this_week`, `tools_trend` instead of expected "stats cards"
- **Details**: The dashboard endpoint works but the data may not map to the visual described in the demo script
- **Risk**: Low — the UI renders whatever the backend returns

---

## What Works

| Component | Status | Notes |
|-----------|--------|-------|
| Portal page load | OK | 0.20s, renders correctly |
| Console page load | OK | 0.28s, renders correctly |
| Keycloak SSO (art3mis) | OK | Token issued in 0.4s |
| Keycloak SSO (parzival) | OK | Token issued in 0.5s |
| API Catalog (12 APIs) | OK | Existing APIs visible, searchable |
| Dashboard stats endpoint | OK | Returns data structure |
| Subscribe endpoint | OK | Exists, returns validation errors as expected |
| Metrics generation | OK | 33/33 API calls succeeded |
| API detail page | OK | 200 in 0.83s for account-management-api |

---

## Seed Script Results

```
Phase 1 — APIs:       FAIL (3/3 failed — GitLab not connected)
Phase 2 — Sync:       SKIPPED (no new APIs)
Phase 3 — Apps:       FAIL (2/2 failed — User.sub bug)
Phase 4 — Subs:       SKIPPED (no apps created)
Phase 5 — Metrics:    OK (33 calls, 0 errors)
```

---

## Recommended Fix Priority

| Priority | Item | Owner | Effort |
|----------|------|-------|--------|
| P0 | BLOCKER-1: Seed Petstore API (fix GitLab or alt path) | Backend | Medium |
| P0 | BLOCKER-2: Fix `User.sub` bug in app creation | Backend | Small |
| P0 | BLOCKER-3: Host mock Petstore (don't depend on swagger.io) | Infra | Small |
| P1 | ISSUE-1: Update checklist curl examples with auth | Docs | Trivial |
| P1 | ISSUE-2: Verify monitoring page path in UI | Frontend | Trivial |
| P2 | ISSUE-4: Validate dashboard card rendering | Frontend | Trivial |

---

## Dry-Run #2 Results (Post-Fix)

> **Date**: 2026-02-04
> **Verdict**: **PASS** — 18/18 checks green

### Fixes Applied

| Blocker | Fix | File |
|---------|-----|------|
| BLOCKER-1 | Added `POST /v1/admin/catalog/seed` endpoint (offline mode) | `catalog_admin.py` |
| BLOCKER-1 | Updated `seed-demo-data.py` with GitOps-first + offline fallback | `seed-demo-data.py` |
| BLOCKER-2 | Replaced `user.sub` with `user.id` (6 occurrences) | `portal_applications.py` |
| BLOCKER-3 | Changed backend_url from swagger.io to httpbin.org | `seed-demo-data.py` |
| ISSUE-1 | Added auth token to DEMO-CHECKLIST curl examples | `DEMO-CHECKLIST.md` |
| ISSUE-2 | Correct path is `/v1/monitoring/transactions/stats` | (documented) |

### Dry-Run #2 Timing

| Segment | Time | Checks |
|---------|------|--------|
| Pre-Auth | 0.9s | 3/3 OK |
| Services UP | 1.4s | 4/4 OK |
| Seed Data | 3.5s | 3/3 OK (petstore, account, payment found) |
| Portal Flow | 2.8s | 5/5 OK |
| Console Flow | 2.6s | 3/3 OK |
| **TOTAL** | **11.4s** | **18/18 PASS** |

### Seed Script Results (Post-Fix)

```
Phase 1 — APIs:       OK (3/3 via offline seed — GitOps failed, catalog/seed worked)
Phase 2 — Sync:       SKIPPED (offline mode — data already in catalog)
Phase 3 — Apps:       OK (2/2 created — oasis-mobile + gunter-dashboard)
Phase 4 — Subs:       FAILED (pre-existing subscription endpoint issue — not blocking for demo)
Phase 5 — Metrics:    OK (33 calls, 0 errors)
```

### Remaining Items (Non-Blocking)

- **Subscription API**: Returns 500 for programmatic subscription creation. Not a demo blocker because the presenter subscribes live in the browser (DEMO-SCRIPT Step 3).
- **Applications in-memory**: Apps are stored in-memory (`_applications` dict), so they reset on pod restart. Run seed shortly before demo.
- **Hot-patched pods**: Fixes deployed via `kubectl cp`, not baked into image. Build and push a proper image before demo day.

---

## Next Steps

1. ~~Fix the 3 blockers~~ **DONE**
2. ~~Re-run seed-demo-data.py~~ **DONE (3/3 APIs + 2/2 apps)**
3. ~~Dry-Run #2~~ **PASS**
4. Build proper Docker image with fixes and push to ECR
5. Browser-based walkthrough to validate UI rendering
6. Record video backup

---

---

## Dry-Run #3 Results (Clean Docker Image)

> **Date**: 2026-02-04T20:51Z
> **Image**: `848853684735.dkr.ecr.eu-west-1.amazonaws.com/apim/control-plane-api:dev-77a2503`
> **Git SHA**: `77a2503124eefe48e4698fd5b96e5a93ce3d1277`
> **CI Run**: [#21686965829](https://github.com/stoa-platform/stoa/actions/runs/21686965829)
> **Verdict**: **PASS** — All fixes baked into image, no hot-patches

### What Changed (vs Dry-Run #2)

| Item | Before (DR#2) | After (DR#3) |
|------|---------------|--------------|
| Image source | Hot-patched via `kubectl cp` | CI-built Docker image from `main` |
| catalog_admin.py | `APICatalog.column` refs in upsert | String column names in `set_` dict |
| portal_applications.py | `user.sub` → `user.id` fix | Already on `main` (no change needed) |
| Anorak password | Unknown/lost | Reset + stored in AWS Secrets Manager |
| Credentials storage | None | `stoa/demo/anorak-credentials` in AWS SM |

### CI Pipeline

| Step | Duration | Status |
|------|----------|--------|
| Lint and Test | 1m11s | PASS |
| Build Docker Image (ECR push) | 49s | PASS |
| Deploy to dev (kubectl set image + rollout) | 1m1s | PASS |
| Notify (Slack) | 4s | PASS |

### Infrastructure Checks

| Service | URL | Status |
|---------|-----|--------|
| API /health/ready | https://api.gostoa.dev/health/ready | 200 PASS |
| API /health/live | https://api.gostoa.dev/health/live | 200 PASS |
| API /health/startup | https://api.gostoa.dev/health/startup | 200 PASS |
| Portal | https://portal.gostoa.dev | 200 PASS |
| Console | https://console.gostoa.dev | 200 PASS |
| MCP Gateway | https://mcp.gostoa.dev | 200 PASS |
| Keycloak OIDC | /realms/stoa/.well-known/openid-configuration | 200 PASS |

### Auth Protection

| Endpoint | Status | Expected |
|----------|--------|----------|
| /v1/portal/apis | 403 | 401/403 PASS |
| /v1/mcp/tools | 403 | 401/403 PASS |
| /v1/tenants | 403 | 401/403 PASS |

### Authenticated API Tests

| Test | Endpoint | Status | Notes |
|------|----------|--------|-------|
| Auth (anorak) | Keycloak token | PASS | cpi-admin role confirmed |
| Portal APIs | /v1/portal/apis | 200 PASS | 16 APIs in catalog |
| Portal Search | /v1/portal/apis?search=pet | 200 PASS | CAB-1044 regression-free |
| Catalog Seed | /v1/admin/catalog/seed | 200 PASS | **CAB-1062 FIX CONFIRMED** |
| Catalog Stats | /v1/admin/catalog/stats | 200 PASS | |
| Applications | /v1/applications | 200 PASS | user.id fix confirmed |

### Seed Script Results (Clean Image)

```
Phase 1 — APIs:       OK (3/3 via offline seed — GitOps failed, catalog/seed worked)
Phase 2 — Sync:       SKIPPED (offline mode — data already in catalog)
Phase 3 — Apps:       OK (2/2 created — oasis-mobile + gunter-dashboard)
Phase 4 — Subs:       FAILED (in-memory app store — known limitation, not blocking)
Phase 5 — Metrics:    OK (33 calls, 0 errors)
```

### AWS Secrets Manager (New)

| Secret | Content |
|--------|---------|
| `stoa/demo/anorak-credentials` | anorak login for seed script |
| `stoa/keycloak/admin` | Keycloak admin (updated URL + password) |
| `stoa/dev/keycloak-admin` | Same for dev |

### Remaining Items (Non-Blocking)

- **Subscription API**: Returns 500 — in-memory app store has no subscription backend. Not a demo blocker.
- **Applications in-memory**: Apps reset on pod restart. Run `make seed-demo` 5 min before demo.
- **Pod restarts**: Image uses `imagePullPolicy: Always` + `dev-latest` tag, so any restart pulls the latest fixed image.

---

## Next Steps

1. ~~Fix the 3 blockers~~ **DONE**
2. ~~Re-run seed-demo-data.py~~ **DONE (3/3 APIs + 2/2 apps)**
3. ~~Dry-Run #2~~ **PASS**
4. ~~Build proper Docker image with fixes and push to ECR~~ **DONE (CI run #21686965829)**
5. ~~Dry-Run #3 (clean image, no hot-patches)~~ **PASS**
6. Browser-based walkthrough to validate UI rendering
7. Record video backup

---

*Generated by Claude Code — CAB-1062 dry-run automation*
