# Test Quality Audit Report — CAB-1951

> Generated: 2026-04-03 | Auditor: Claude (AI Factory) | Scope: all 4 components

## Executive Summary

| Metric | Value |
|--------|-------|
| Total test files | ~800 |
| Total tests (approx) | ~15,800 |
| Coverage | 91% (vanity metric) |
| Regressions caught by tests (CAB-1944) | **0 / 5** |

**Root cause**: ~30% of tests mock the boundary they claim to test. They validate implementation (mock was called), not behavior (system works correctly).

## Methodology

Each test file classified into one of 5 categories:

| Category | Definition | Action |
|----------|-----------|--------|
| **KEEP** | Tests real business logic, RBAC, state machines, edge cases, error handling | Retain |
| **BOUNDARY-MOCK** | Mocks the exact boundary it tests (adapter mocks httpx, router mocks repo) | Kill or replace |
| **SMOKE-ONLY** | Trivial assertions: status 200, "renders without crashing", mock call count | Kill |
| **STRUCTURAL** | Tests abstract method bodies, dataclass defaults, model field existence | Kill |
| **INTEGRATION** | Uses real DB, real HTTP transport, MSW, tower::ServiceExt | Retain + promote |

---

## Control Plane API (350 files, ~7,400 tests)

### Distribution

| Category | Files | Tests (approx) | % of total |
|----------|-------|----------------|------------|
| KEEP | 227 | ~4,800 | 65% |
| BOUNDARY-MOCK | 89 | ~2,000 | 27% |
| SMOKE-ONLY | 17 | ~200 | 3% |
| STRUCTURAL | 11 | ~250 | 3% |
| INTEGRATION | 6 | ~44 | <1% |

### BOUNDARY-MOCK files (89 — kill candidates)

**Adapter tests** (7 files, ~310 tests) — mock httpx entirely:
- `test_apigee_adapter.py` (63), `test_aws_apigw_adapter.py` (48), `test_azure_apim_adapter.py` (53)
- `test_gravitee_adapter.py` (35), `test_kong_adapter.py` (38), `test_stoa_adapter.py` (15)
- `test_webmethods_adapter.py` (58) — **rewrite as integration in Phase 3**

**Router tests** (70+ files, ~1,400 tests) — mock entire repo layer, assert status codes:
- Pattern: `MockRepo.return_value.method = AsyncMock(return_value=...)` + `assert status_code == 200`
- Examples: `test_apis_router.py`, `test_consumers_router.py`, `test_subscriptions_router.py`, `test_deployments_router.py`
- **Exception**: router tests that verify RBAC (403/401 for wrong roles) → reclassify as KEEP

**Other boundary mocks** (12 files):
- `test_gateway_adapter_interface.py` (23) — tests abstract `...` body via MagicMock
- `test_backend_api_repo.py` (22), `test_catalog_repo.py` (30) — mock DB session entirely

### SMOKE-ONLY files (17 — kill candidates)

- `test_adapter_template.py` (3), `test_auth_operator.py` (3), `test_database.py` (6)
- `test_deploy_mode.py` (11), `test_email.py` (5), `test_environments.py` (3)
- `test_events.py` (4), `test_health.py` (8), `test_logging_config.py` (20)
- `test_prometheus_client.py` (52), `test_prometheus_helpers.py` (26)
- `test_loki_client.py` (27), `test_platform_status.py` (7)
- `test_gateway_import_service.py` (8), `test_gateway_metrics.py` (4)
- `test_personal_tenant.py` (6), `test_external_mcp_servers_internal.py` (5)

### STRUCTURAL files (11 — kill candidates)

- `test_catalog_schemas.py` (15), `test_chat_models.py` (28), `test_chat_schemas.py` (37)
- `test_federation_models.py` (35), `test_federation_schemas.py` (40)
- `test_onboarding_models.py` (11), `test_onboarding_schemas.py` (19)
- `test_platform_schemas.py` (16), `test_traces_db_model.py` (8), `test_traces_pydantic.py` (24)
- `test_promotion_model.py` (22)

### KEEP highlights (valuable tests)

- **Regression tests** (20 files): `test_regression_cab_*.py` — guards against specific past bugs
- **Business logic**: `test_contract_lifecycle.py`, `test_billing.py`, `test_sync_engine.py`
- **Security**: `test_security_posture.py` (101), `test_pii_masking.py` (51), `test_rbac.py` (20)
- **Services**: `test_keycloak_service.py` (83), `test_git_service.py` (135), `test_diagnostic_service.py` (82)

---

## Console UI (162 files, ~2,100 tests)

### Distribution

| Category | Files | Tests (approx) | % of total |
|----------|-------|----------------|------------|
| KEEP | 91 | ~1,300 | 62% |
| STRUCTURAL | 36 | ~300 | 17% |
| BOUNDARY-MOCK | 26 | ~400 | 12% |
| SMOKE-ONLY | 9 | ~80 | 4% |
| INTEGRATION | 0 | 0 | 0% |

### SMOKE-ONLY files (9 — kill candidates)

- `App.test.tsx` (5) — 10+ vi.mock(), only asserts "renders Dashboard heading"
- `pages/Dashboard.test.tsx` (8), `pages/Dashboard/PlatformDashboard.test.tsx` (12)
- `pages/AdminProspects.test.tsx` (9), `pages/Tenants.test.tsx` (9)
- `pages/GatewayStatus.test.tsx` (13), `pages/GatewayObservability/*.test.tsx` (11)
- `pages/ExternalMCPServers/ExternalMCPServerDetail.test.tsx` (8)
- `__tests__/regression/CAB-1887-gateway-mock-data.test.tsx` (5)

### BOUNDARY-MOCK files (26 — kill candidates)

**Service layer tests** (11 files) — mock fetch/axios, assert mock was called:
- `services/api.test.ts` (98), `services/mcpGatewayApi.test.ts` (19)
- `services/federationApi.test.ts` (13), `services/errorSnapshotsApi.test.ts` (11)
- `services/backendApisApi.test.ts` (10), `services/gatewayApi.test.ts` (7)
- `services/skillsApi.test.ts` (7), `services/mcpConnectorsApi.test.ts` (6)
- `services/externalMcpServersApi.test.ts` (9), `services/proxyBackendService.test.ts` (9)
- `services/diagnosticService.test.ts` (4)

**Component tests with heavy mocking** (15 files):
- `contexts/AuthContext.test.tsx` (13) — **mixed: has valuable RBAC logic, keep**
- `components/PermissionGate.test.tsx` (11) — **mixed: RBAC matrix, keep**
- `components/PlatformStatus.test.tsx` (15), `components/tools/UsageChart.test.tsx` (12)
- Various page/hook tests with 5-8 vi.mock() + minimal interaction

### STRUCTURAL files (36 — kill candidates)

- Minimal render tests: `DriftDetection/index.test.tsx` (1), `GatewayObservability/index.test.tsx` (1)
- Chart component stubs: `SparklineChart.test.tsx` (15), `ErrorBreakdown.test.tsx` (3)
- Config/utility tests: `config.test.ts` (14), `utils/navigation.test.ts` (10)
- Hook smoke tests: `useDebounce.test.ts` (3), `useMediaQuery.test.ts` (4)

### Notable: MSW exists but is unused

`control-plane-ui/src/test/mocks/` contains:
- `server.ts` — `setupServer()` from msw/node
- `handlers.ts` — 158 lines of HTTP handlers
- `data.ts` — mock response data

**No test file calls `server.listen()`**. Phase 3 will activate this.

---

## Portal (141 files, ~1,800 tests)

### Distribution

| Category | Files | Tests (approx) | % of total |
|----------|-------|----------------|------------|
| KEEP | 74 | ~700 | 39% |
| BOUNDARY-MOCK | 40 | ~400 | 22% |
| STRUCTURAL | 24 | ~200 | 13% |
| SMOKE-ONLY | 3 | ~48 | 3% |
| INTEGRATION | 0 | 0 | 0% |

### SMOKE-ONLY files (3 — kill candidates)

- `pages/__tests__/APICatalog.test.tsx` (16), `pages/__tests__/Home.test.tsx` (13)
- `pages/__tests__/MarketplacePage.test.tsx` (19)

### BOUNDARY-MOCK files (40 — kill candidates)

**Service layer tests** (24 files) — vi.mock on fetch, assert call count:
- `services/api.test.ts` (19), `services/mcpServers.test.ts` (21)
- `services/apiCatalog.test.ts` (15), `services/certificateValidator.test.ts` (15)
- `services/subscriptions.test.ts` (14), `services/marketplace.test.ts` (9)
- Plus 18 more service test files (4-12 tests each)

**Component tests** (16 files) — heavy mocking:
- `components/common/PermissionGate.test.tsx` (14) — **mixed: RBAC, keep**
- `pages/Home.test.tsx` (8), `pages/Unauthorized.test.tsx` (10)
- Various dashboard/layout components

### STRUCTURAL files (24 — kill candidates)

- Skeleton tests: `DashboardSkeleton.test.tsx` (8), `ServerCardSkeleton.test.tsx` (9), `StatCardSkeleton.test.tsx` (9), `TableSkeleton.test.tsx` (13)
- Pure display: `Skeleton.test.tsx` (14), `ApplicationCard.test.tsx` (14), `QuotaBar.test.tsx` (19)
- Utility: `format.test.ts` (14), `SkipLink.test.tsx` (2)
- Small service tests (2-3 tests each): `apiComparison.test.ts`, `auditLog.test.ts`, `errorTracking.test.ts`, etc.

### No MSW infrastructure

Portal has no MSW setup. Phase 3 will create `portal/src/test/mocks/`.

---

## Gateway (145 test modules, ~4,400 tests)

### Distribution

| Category | Modules | Tests (approx) | % of total |
|----------|---------|----------------|------------|
| KEEP (inline) | ~160 | ~3,800 | 86% |
| CONTRACT | 5 | ~35 | <1% |
| INTEGRATION | 9 | ~52 | 1% |
| SECURITY | 3 | ~21 | <1% |
| RESILIENCE | 3 | ~14 | <1% |
| SMOKE-ONLY | ~23 | ~100 | 2% |

### SMOKE-ONLY (23 inline modules — kill candidates)

Inline `#[cfg(test)]` modules that only test:
- Struct creation / field access
- Config parsing round-trips
- Load balancer round-robin cycles
- Cost calculation trivial math
- Fingerprint normalization (base64/hex)

### KEEP highlights

- **Contract tests** (35 tests): MCP spec compliance, OAuth metadata snapshots, A2A JSON-RPC
- **Security tests** (21 tests): SSRF blocklist (11 tests — excellent), bearer validation, header injection, admin leakage
- **Resilience tests** (14 tests): circuit breaker state machine, fault injection, concurrency
- **Integration tests** (52 tests): tool lifecycle, LLM proxy, auth pipeline, MCP discovery

### No property-based tests

Zero proptest/quickcheck usage. Gap for: JSON-RPC parsing, JWT validation, spec parsing, random API names.

---

## Cross-Component Summary

| Component | Total Files | KEEP | Kill Candidates | Kill % |
|-----------|------------|------|-----------------|--------|
| CP API | 350 | 233 | 117 | **33%** |
| Console UI | 162 | 91 | 71 | **44%** |
| Portal | 141 | 74 | 67 | **47%** |
| Gateway | ~185 | ~175 | ~23 | **12%** |
| **Total** | **~838** | **~573** | **~278** | **33%** |

### Kill priority (Phase 2 order)

1. **CP API adapter mocks** (7 files, ~310 tests) — highest risk, CAB-1944 regressions here
2. **CP API router mocks** (70 files, ~1,400 tests) — bulk of mechanical tests
3. **UI/Portal service mocks** (35 files, ~500 tests) — no real HTTP validation
4. **UI/Portal smoke tests** (12 files, ~130 tests) — zero value
5. **Structural/schema tests** (71 files, ~500 tests) — coverage padding only
6. **Gateway inline smoke** (23 modules, ~100 tests) — lowest priority, small count

### Integration test gaps (Phase 3 targets)

| Boundary | Current Tests | Needed |
|----------|--------------|--------|
| CP API → webMethods REST | 0 real HTTP | 8 (CAB-1944 regressions) |
| CP API → STOA Gateway | 0 real HTTP | covered by gateway integration |
| Console UI → CP API | 0 (MSW unused) | 4 (activate MSW) |
| Portal → CP API | 0 (no MSW) | 4 (create MSW) |
| Gateway sync engine | 3 (basic) | 3 more (multi-cycle, stale, rate-limit) |
| Property-based (any) | 0 | future work |

---

## CAB-1944 Regression Analysis

| Bug | Test File That Should Catch It | Exists? | Why Not? |
|-----|-------------------------------|---------|----------|
| em-dash in apiName | `test_webmethods_adapter.py` | Yes but mocked | Mock accepts any string |
| oauth2 vs OAUTH2 | `test_webmethods_adapter.py` | Yes but mocked | Mock doesn't validate enums |
| admin_token missing → 401 | `test_stoa_adapter.py` | Yes but mocked | Mock always returns 200 |
| externalDocs object vs array | `test_webmethods_adapter.py` | Yes but mocked | Mock doesn't parse payload |
| Infinite retry loop | `test_sync_engine.py` | Yes but 1 cycle | Test runs 1 sync cycle only |

**All 5 regressions were at boundaries where mocks hid the real failure mode.**

---

## New Rule Added

**Boundary Integrity Rule** added to `.claude/rules/testing-standards.md`:
> Never generate tests that mock the boundary under test.

See `testing-standards.md` for the full rule with per-layer guidance.

---

## Recommendations

1. **Phase 2**: Delete ~278 files / ~2,900 tests (33% reduction). Temporarily lower coverage thresholds.
2. **Phase 3**: Add 20+ integration tests at the 5 identified boundaries. Restore thresholds.
3. **Phase 4**: Gate CI on integration tests (separate job, runs on PR + main).
4. **Future**: Add property-based tests for JSON-RPC, JWT, OpenAPI spec parsing.
