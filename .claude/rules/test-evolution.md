---
description: Rules for keeping tests in sync with code changes
globs: "**/tests/**,**/test_*,**/*.test.*,**/*.spec.*"
---

# Test Evolution — Keep Tests in Sync with Code

## Trigger

When a component, page, or hook is modified, verify its tests exist and are up to date.

## Rules

### Test-First Rule (DEFAULT for feat/fix)
For all `feat()` and `fix()` PRs, write failing tests BEFORE implementation code:
1. Analyze the requirement or bug → identify expected behavior
2. Write test(s) that assert the expected behavior → they should FAIL
3. Implement the code to make tests pass
4. Verify all tests green, then commit

This is Pattern 3 default (merged from Pattern 7 Osmani). Code-first (Pattern 5) is only for `refactor()`, `chore()`, `docs()`, `style()`.

### Ratchet Rule
Coverage thresholds in `vitest.config.ts` / `pyproject.toml` are floors, never ceilings.
- Coverage can go UP (raise the threshold).
- Coverage MUST NOT go DOWN. If a change lowers coverage, add tests in the same PR.

### Persona Rule
Any page or component with RBAC-conditional rendering (checks `hasPermission`, `hasRole`, or role-based UI) MUST have tests for all 4 personas:
- `cpi-admin`, `tenant-admin`, `devops`, `viewer`
- Use `describe.each<PersonaRole>([...])` pattern.

### Helpers-First Rule
Use shared test helpers — never duplicate mock setup inline:
- **Console**: `control-plane-ui/src/test/helpers.tsx` (`createAuthMock`, `renderWithProviders`, mock data factories)
- **Portal**: `portal/src/test/helpers.tsx` (same pattern)

When `vi.mock('../contexts/AuthContext')` appears inline in >2 test files, refactor to use `createAuthMock` from helpers.

### Mock Reset Rule
When a test overrides a mock (e.g., `mockFn.mockRejectedValue()`), `vi.clearAllMocks()` does NOT reset implementations. Always re-initialize mocks in `beforeEach`:
```typescript
beforeEach(() => {
  vi.clearAllMocks();
  mockGetData.mockResolvedValue(defaultData); // Re-set after clearAllMocks
  vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
});
```

### Test Adjacency Rule
New component = tests in the same PR. No "we'll add tests later".

### E2E Co-Evolution Rule
Feature/fix tickets MUST include Playwright scenario updates in the same PR:
- New endpoint → E2E happy path + error case
- Changed behavior → Update affected `@smoke` or `@critical` scenarios
- UI change → Update page object + assertions

No "we'll add E2E later" tickets. If E2E infra blocks the PR, tag `@wip` and document in DoD.

### Regression Test Rule
Every `fix()` PR MUST include a dedicated regression test that reproduces the original bug:
- **Python**: `test_regression_cab_XXXX_short_description()` in `tests/test_regression_*.py`
- **TypeScript**: `describe('regression/CAB-XXXX', ...)` in `src/__tests__/regression/`
- **Rust**: `fn regression_description()` inline in `#[cfg(test)] mod tests`
- **E2E**: Add `@regression` tag to scenarios that guard against specific bug fixes

Each regression test MUST document: PR number, ticket ID, root cause, and the invariant being protected.

CI enforces this via the `regression-guard.yml` workflow (**blocking** — required check). Bypass: `skip-regression` label for documented hotfixes.

### Detection
When reviewing a PR, check:
1. Modified files in `src/pages/` → corresponding `.test.tsx` exists?
2. New `vi.mock('AuthContext')` inline → should use `createAuthMock` from helpers?
3. Coverage diff → threshold still met?
4. PR title starts with `fix(` → regression test present?
