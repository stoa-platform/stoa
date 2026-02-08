# Smoke Test Report -- Cycle 6

**Date**: 2026-02-08 11:01:43 UTC
**Domain**: gostoa.dev
**Protocol**: https
**Executed from**: Local workstation (macOS)

## Results

```
================================================================
  STOA Platform Smoke Test Gate (Level 1)
  CAB-1043
================================================================

  Base Domain : gostoa.dev
  Protocol    : https
  Timestamp   : 2026-02-08 11:01:43 UTC

----------------------------------------------------------------

  AUDIT-1  Portal HTTP 200 .................. PASS (169ms)
  AUDIT-2  Keycloak OIDC .................... PASS (189ms)
  AUDIT-3  MCP Gateway ...................... PASS (166ms)
  AUDIT-4  Control Plane API ................ PASS (967ms)
  AUDIT-5  Catalogue >= 12 APIs ............. FAIL (got 0)
  AUDIT-6  Tokens (personas) ................ FAIL (no credentials in env)
  AUDIT-7  DNS 4/4 .......................... PASS (194ms)
  AUDIT-8  TLS certificates ................. PASS (530ms)

----------------------------------------------------------------

  SCORE: 6/8 -- GATE FAILED (minimum 8/8)
  BLOCKING FAILURES: 1 (AUDIT-1, AUDIT-2, or AUDIT-6)
```

## Verdict

**GATE FAILED** -- 6/8

## Analysis

| Check | Status | Notes |
|-------|--------|-------|
| AUDIT-1 Portal HTTP 200 | PASS | Portal frontend is up and serving (169ms) |
| AUDIT-2 Keycloak OIDC | PASS | OIDC discovery endpoint responds correctly (189ms) |
| AUDIT-3 MCP Gateway | PASS | MCP Gateway health endpoint is healthy (166ms) |
| AUDIT-4 Control Plane API | PASS | Control Plane API /health responds (967ms, slightly slow) |
| AUDIT-5 Catalogue >= 12 APIs | FAIL | Portal API `/v1/portal/apis` returned 0 APIs. The endpoint requires authentication; without a Bearer token the response is empty or rejected. This check needs persona tokens from AUDIT-6 to work correctly. |
| AUDIT-6 Tokens (personas) | FAIL | No persona credentials were set in environment variables (`ALEX_USER`, `PARZIVAL_USER`, `SORRENTO_USER`). This is expected when running locally without access to secrets. |
| AUDIT-7 DNS 4/4 | PASS | All 4 subdomains (portal, api, mcp, auth) resolve correctly |
| AUDIT-8 TLS certificates | PASS | All 4 TLS certificates are valid and not expired |

## Observations

1. **Infrastructure is healthy**: 6 of 8 checks pass, confirming that DNS, TLS,
   and all 4 services (Portal, Keycloak, MCP Gateway, Control Plane API) are
   operational.

2. **AUDIT-5 depends on AUDIT-6**: The catalogue endpoint requires authentication.
   A future improvement could chain these: acquire a token in AUDIT-6, then use it
   for the authenticated catalogue call in AUDIT-5.

3. **AUDIT-6 requires secrets**: The persona credentials (alex, parzival, sorrento)
   must be provided via environment variables. In CI, these would come from GitHub
   Actions secrets. For local runs, developers need to export them from a secrets
   manager or `.env` file.

4. **API response time**: Control Plane API /health took 967ms which is above the
   typical <200ms target. This may warrant investigation (cold start, database
   connection pool warmup, or network latency from local workstation).

## Next Steps

- [ ] Configure CI secrets for persona credentials to enable AUDIT-6
- [ ] Consider making AUDIT-5 use the token from AUDIT-6 when available
- [ ] Investigate Control Plane API latency (967ms on /health)
- [ ] Integrate `npm run test:smoke` into CI pipeline as a post-deploy gate
