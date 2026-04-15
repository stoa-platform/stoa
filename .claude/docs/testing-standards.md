<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
description: Testing standards, frameworks, thresholds, and test evolution rules
globs: "**/tests/**,**/test_*,**/*.test.*,**/*.spec.*,e2e/**"
---

# Testing Standards

## Frameworks & Thresholds

| Component | Framework | Coverage | Run Command |
|-----------|-----------|----------|-------------|
| control-plane-api | pytest + pytest-asyncio (auto) | **70%** | `pytest --cov=src --cov-fail-under=70 --ignore=tests/test_opensearch.py -q` |
| mcp-gateway | pytest | **40%** | `pytest --cov=src --cov-fail-under=40 -q` |
| control-plane-ui | vitest + RTL | ESLint <100 warnings | `npm run test -- --run` |
| portal | vitest + RTL | ESLint 0 warnings | `npm run test -- --run` |
| stoa-gateway | cargo test | Zero clippy warnings | `cargo test --all-features` |
| e2e | Playwright + BDD | N/A | `npx playwright test` (from `e2e/`) |

- Python: file naming `test_*.py` or `*_test.py`, markers `@slow`, `@integration`, `@unit`
- TypeScript: vitest (NOT Jest), v8 coverage provider
- E2E: Gherkin `.feature` files, markers `@smoke`, `@critical`, `@portal`, `@console`, `@gateway`

## Shared Test Helpers (React)

- **Console**: `control-plane-ui/src/test/helpers.tsx`
- **Portal**: `portal/src/test/helpers.tsx`

Key exports: `createAuthMock(role)`, `renderWithProviders(ui, options?)`, mock data factories.
4 personas: `cpi-admin`, `tenant-admin`, `devops`, `viewer`.

## Test Evolution Rules

### Test-First Rule (DEFAULT for feat/fix)
Write failing tests BEFORE implementation code:
1. Analyze requirement/bug → identify expected behavior
2. Write test(s) that assert expected behavior → they should FAIL
3. Implement code to make tests pass
4. Verify all tests green, then commit

Code-first (Pattern 5) is only for `refactor()`, `chore()`, `docs()`, `style()`.

### Ratchet Rule
Coverage thresholds are floors, never ceilings. Coverage MUST NOT go DOWN.

### Persona Rule
RBAC-conditional components MUST have tests for all 4 personas. Use `describe.each<PersonaRole>([...])`.

### Helpers-First Rule
Use shared test helpers — never duplicate mock setup inline. When `vi.mock('AuthContext')` appears in >2 files, refactor to `createAuthMock`.

### Mock Reset Rule
`vi.clearAllMocks()` does NOT reset implementations. Re-initialize mocks in `beforeEach`:
```typescript
beforeEach(() => {
  vi.clearAllMocks();
  mockGetData.mockResolvedValue(defaultData);
  vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
});
```

### Test Adjacency Rule
New component = tests in the same PR. No "we'll add tests later".

### E2E Co-Evolution Rule
Feature/fix tickets MUST include Playwright scenario updates in the same PR. If E2E infra blocks, tag `@wip`.

### Regression Test Rule
Every `fix()` PR MUST include a regression test:
- **Python**: `test_regression_cab_XXXX_short_description()` in `tests/test_regression_*.py`
- **TypeScript**: `describe('regression/CAB-XXXX', ...)` in `src/__tests__/regression/`
- **Rust**: `fn regression_description()` inline in `#[cfg(test)] mod tests`
- **E2E**: `@regression` tag on guarding scenarios

CI enforces via `regression-guard.yml` (blocking). Bypass: `skip-regression` label.

### Boundary Integrity Rule (CAB-1951)
Never generate tests that mock the boundary under test. If a test for `WebMethodsAdapter`
replaces `GatewayAdminService` with a mock, it tests nothing — it asserts that your mock
returns what you told it to.

| Layer | Wrong | Right |
|-------|-------|-------|
| **Python adapters** | `unittest.mock.AsyncMock` on the HTTP client | `httpx.MockTransport` with realistic payloads |
| **Python routers** | Patch entire repository + assert `status_code == 200` | FastAPI `TestClient` with real (in-memory) DB |
| **React pages** | 8+ `vi.mock()` + `getByText('Dashboard')` | MSW to intercept `fetch`, render with real providers |
| **Rust HTTP** | Inline mock returning hardcoded `Ok(())` | `axum::test` helpers or `mockito` crate |

**Why**: CAB-1944 shipped 5 regressions at mocked boundaries. 5,700 tests, 0 caught them.

**How to apply**: Before writing a test, ask: "If the real dependency had a bug, would this
test catch it?" If the answer is no (because the dependency is mocked), redesign the test.

### Accessibility & Visual Regression Rule (CAB-1989)

UI changes to Console or Portal trigger 3 CI gates automatically. Follow these rules:

**data-testid on new components**: Every new page or data-displaying component MUST have `data-testid` attributes following the convention in `docs/DATA-TESTID-CONVENTION.md`. Pattern: `<section>-<element>[-<variant>]`. Dynamic values use suffixes: `-count`, `-timestamp`, `-duration` (auto-masked in visual regression).

**axe-core a11y**: `e2e-a11y-gate.yml` scans 10 Console pages for WCAG 2.1 AA violations. If you add a new page to Console, add it to `e2e/smoke-mock/a11y-axe.smoke.ts` CONSOLE_PAGES array. Current threshold: `critical` (env `A11Y_IMPACT_THRESHOLD`). Helper: `e2e/fixtures/axe-helper.ts`.

**Visual regression**: `e2e-visual-regression.yml` compares screenshots against golden baselines in `e2e/golden/`. If your PR intentionally changes UI appearance:
1. Regenerate baselines in Docker: `cd e2e && docker run --rm -v $(pwd):/work -w /work mcr.microsoft.com/playwright:v1.58.2-jammy npx playwright test --config=visual/playwright.config.ts --update-snapshots`
2. Review: `git diff --stat e2e/golden/`
3. Commit updated PNGs in the same PR
4. Mask helper (`e2e/visual/mask-helper.ts`) auto-masks `-count`/`-timestamp`/`-duration` testids

**ARIA roles**: New interactive containers need semantic roles (`role="list"`, `role="tablist"`, `role="region"` with `aria-label`). See `e2e/fixtures/aria-helpers.ts` for assertion helpers.

### Detection Checklist
1. Modified `src/pages/` → corresponding `.test.tsx` exists?
2. New `vi.mock('AuthContext')` inline → should use `createAuthMock`?
3. Coverage diff → threshold still met?
4. PR title `fix(` → regression test present?
5. New test mocks the boundary under test? → redesign per Boundary Integrity Rule
6. Modified Console/Portal UI → `data-testid` on new elements? ARIA roles on containers?
7. UI appearance changed → golden baselines updated in `e2e/golden/`?

### Evidence Archive Rule

After any Playwright run, archive results into `docs/audits/`. See `e2e-audit.md` for the single canonical process.
**Never** use `audit/<TICKET>/` or leave results in `e2e/test-results/` — both are ephemeral.
