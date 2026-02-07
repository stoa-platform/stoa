## CAB-1116 — Test Automation Strategy (21 SP, 5 phases)

### Vue d'ensemble

| Phase | Sujet | Status | DoD |
|-------|-------|--------|-----|
| Phase 1 | Console UI unit tests (MSW) | ✅ DONE | 25 test files, 50.98% coverage, 232 tests PASS |
| Phase 2 | Portal unit tests + API 45%→65% | ⬜ Pending | Portal 10+ files, API pytest 65% |
| Phase 3 | Integration tests + contract tests | ⬜ Pending | API↔UI schema validation in CI |
| Phase 4 | E2E completeness 52→75+ scenarios | ⬜ Pending | 75+ Playwright scenarios, all @smoke pass |
| Phase 5 | Quality gates | ⬜ Pending | Coverage ratchet, pre-commit hooks, security gates |

---

### Phase 1 — Console UI Unit Tests ✅ DONE

#### Résultat final
- **25 test files**, **232 tests**, tous PASS
- **50.98% statement coverage** (seuil: 50%)
- **4 mock files** MSW: `handlers.ts`, `server.ts`, `keycloak.ts`, `data.ts`
- Coverage thresholds relevés: lines 50%, statements 50%, branches 60%, functions 35%

#### Fichiers testés (25)
- `App.test.tsx` (6 tests)
- `components/Layout.test.tsx` (10 tests)
- `components/tools/ToolCard.test.tsx`
- `components/tools/ToolSchemaViewer.test.tsx`
- `contexts/AuthContext.test.tsx`
- `pages/Dashboard.test.tsx` (7 tests)
- `pages/APIs.test.tsx`
- `pages/APIMonitoring.test.tsx` (8 tests)
- `pages/AdminProspects.test.tsx`
- `pages/Applications.test.tsx`
- `pages/Tenants.test.tsx`
- `pages/Gateways/GatewayList.test.tsx`
- `pages/GatewayObservability/GatewayObservabilityDashboard.test.tsx`
- `pages/GrafanaEmbed.test.tsx`
- `pages/IdentityEmbed.test.tsx`
- `pages/LogsEmbed.test.tsx`
- `pages/Deployments.test.tsx` (9 tests) — NEW
- `pages/ErrorSnapshots.test.tsx` (11 tests) — NEW
- `pages/GatewayStatus.test.tsx` (14 tests) — NEW
- `pages/Business/BusinessDashboard.test.tsx` (11 tests) — NEW
- `pages/Operations/OperationsDashboard.test.tsx` (10 tests) — NEW
- `pages/TenantDashboard/TenantDashboard.test.tsx` (10 tests) — NEW
- `pages/ExternalMCPServers/ExternalMCPServersList.test.tsx` (12 tests) — NEW
- `pages/AITools/ToolCatalog.test.tsx` (9 tests) — NEW
- `pages/Gateways/GatewayModesDashboard.test.tsx` (8 tests) — NEW

#### Fichiers NON testés (19 restants — Phase 2+)

**Components (4):**
- `components/PlatformStatus.tsx`
- `components/SyncStatusBadge.tsx`
- `components/tools/QuickStartGuide.tsx`
- `components/tools/UsageChart.tsx`

**Pages (10):**
- `pages/AITools/MySubscriptions.tsx`
- `pages/AITools/ToolDetail.tsx`
- `pages/AITools/UsageDashboard.tsx`
- `pages/ExternalMCPServers/ExternalMCPServerDetail.tsx`
- `pages/ExternalMCPServers/ExternalMCPServerModal.tsx`
- `pages/GatewayDeployments/DeployAPIDialog.tsx`
- `pages/GatewayDeployments/GatewayDeploymentsDashboard.tsx`
- `pages/Gateways/GatewayRegistrationForm.tsx`

**Hooks + Services (non prioritaire):**
- 6 hooks, 5 services — coverage indirecte via page tests

---

### Phase 2 — Portal + API (next)
- Portal: 10+ test files vitest, même pattern MSW
- API: pytest coverage 45%→65%, focus sur endpoints CRUD + RBAC

### Phase 3 — Integration + Contract Tests
- API↔UI schema validation in CI
- Contract tests automatisés

### Phase 4 — E2E Completeness
- 52→75+ Playwright BDD scenarios
- Tous les @smoke pass

### Phase 5 — Quality Gates
- Coverage ratchet (fail if coverage drops)
- Pre-commit hooks (lint + format + type-check)
- Security gates (bandit, npm audit)

---

### Règle de fallback
- **Ne jamais commencer Phase N+1 si Phase N n'est pas 100% DoD**
- Verdict binaire par phase: DONE / NOT DONE
