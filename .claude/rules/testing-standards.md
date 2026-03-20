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

### Detection Checklist
1. Modified `src/pages/` → corresponding `.test.tsx` exists?
2. New `vi.mock('AuthContext')` inline → should use `createAuthMock`?
3. Coverage diff → threshold still met?
4. PR title `fix(` → regression test present?
