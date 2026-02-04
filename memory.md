# STOA Memory

> Dernière MAJ: 2026-02-04 (Session 3 — E2E Validation)

## DONE
- CAB-1044: API Search HTTP 500 — Fixed (escape LIKE wildcards in portal search) — commit 2c5672d8
- CAB-1040: Gateway Routes HTTP 404 — Fixed (disable redirect_slashes to prevent 307 on /mcp) — commit 0c33e21d
- CAB-1042: Vault sealed — Fixed (VaultSealedException + _ensure_unsealed() in both vault clients) — commit 8bbf71b9
- CAB-1041: E2E BDD auth — Fixed (capture/restore sessionStorage for OIDC tokens) — commit 248f9d29
- CLI stoa complète — Python/Typer/Rich, 5 commands, 55 tests, 84% coverage
- E2E tests 100% pass — 24/24 green against live gostoa.dev (Session 3)

## IN PROGRESS
(rien)

## NEXT
- CAB-1060: Docs 20 pages (docs.gostoa.dev)
- CAB-1061: Demo script 5 min
- CAB-1062: Final polish + dry-runs
- CAB-1066: Landing gostoa.dev + Stripe

## BLOCKED
(rien)

## E2E VALIDATION RESULTS (Session 3 — 2026-02-04)

### Run Summary
- **24/24 tests passed** (22.6s total)
- Auth setup: 7/7 personas authenticated with dual OIDC keys (portal + console)
- Portal: 5/5 scenarios pass (catalog visibility, search, filter, RPO personas)
- Console: 5/5 scenarios pass (API list, tenant selector, admin, cross-tenant security)
- Gateway: 6/6 scenarios pass (health, auth rejection, rate limiting, token expiry)
- TTFTC: 1/1 pass — Alex Freelance onboarding in 12.7s (target <120s)

### Bug Fix Verification (Live Environment)
| Bug | Status | Evidence |
|-----|--------|----------|
| CAB-1044: API Search HTTP 500 | VERIFIED | Search test passes; /v1/portal/apis returns 403 (not 500) |
| CAB-1040: Gateway Routes HTTP 404 | VERIFIED | /v1/mcp/tools returns 403 (not 404); MCP root returns 200 |
| CAB-1041: E2E BDD auth | VERIFIED | All 7 personas authenticate; sessionStorage capture works for both OIDC clients |
| CAB-1042: Vault sealed | VERIFIED | Application healthy; no Vault errors during smoke test |

### Smoke Test (2026-02-04 11:18 UTC)
| Endpoint | Status |
|----------|--------|
| api.gostoa.dev /health/ready | 200 |
| api.gostoa.dev /health/live | 200 |
| api.gostoa.dev /health/startup | 200 |
| api.gostoa.dev /v1/portal/apis | 403 (auth required) |
| api.gostoa.dev /v1/mcp/tools | 403 (auth required) |
| portal.gostoa.dev | 200 |
| console.gostoa.dev | 200 |
| mcp.gostoa.dev | 200 |
| auth.gostoa.dev OIDC | 200 |

**Zero HTTP 500 errors** across all endpoints.

### Loki Query
Loki is behind oauth2-proxy — requires Grafana auth for direct queries.
Manual check needed in Grafana: `{job=~".+"} |= "level=error"` over last 5 min.
Grafana healthy at v12.3.1, database OK.

### E2E Fixes Applied (Session 3)
1. **auth.setup.ts**: Cross-app SSO — each persona authenticates on BOTH portal and console, merged sessionStorage with both OIDC client keys (stoa-portal + control-plane-ui)
2. **gateway-access-control.feature**: Replaced fictional API paths with real control-plane-api endpoints
3. **console-isolation.feature**: Data-agnostic tenant assertions (system uses "oasis"/"oasis-gunters" not "high-five"/"ioi")
4. **portal.steps.ts**: Switched to `a[href^="/apis/"]` selector (resilient across CSS class changes)
5. **alex-ttftc.feature**: Simplified to discover flow (steps 1-5); subscription flow deferred until Portal subscription UI is complete
6. **ttftc.steps.ts**: Fixed search step to extract API title (h3) not full card text

## NOTES
- Demo: mardi 24 février 2026
- Présentation "ESB is Dead" même jour
- 2 design partners à closer
- Stack = Python (pas Node)
- Existing CLAUDE.md preserved (more comprehensive than bootstrap version)
- Branch: feat/claude-sprint-feb24
- CAB-1041 root cause: react-oidc-context uses sessionStorage, Playwright storageState() misses it
- CAB-1042 root cause: no sealed check before Vault operations, obscure hvac errors
- Console tenants: actual names are "oasis", "oasis-gunters" (not "high-five", "ioi" from RPO theme)
- Portal OIDC client: stoa-portal; Console OIDC client: control-plane-ui
- TTFTC Alex Freelance: 12.7s from landing to API detail (5 steps)
- Portal has 2 APIs in catalog; Console has 0 APIs per tenant (data seeding needed for richer tests)
