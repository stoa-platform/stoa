---
description: Rules for keeping tests in sync with code changes
globs: "**/tests/**,**/test_*,**/*.test.*,**/*.spec.*"
---

# Test Evolution — Keep Tests in Sync with Code

## Trigger

When a component, page, or hook is modified, verify its tests exist and are up to date.

## Rules

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

### Regression Test Convention
Fix PRs (commits with `fix()` prefix or containing "fix"/"bug" in PR body) MUST include regression tests:

#### Unit/Integration Tests
- Naming: `test_regression_cab_XXXX.py` (for Python) or `test_regression_cab_XXXX.ts` (for TypeScript)
- Location: same directory as unit tests for the affected component
- Content: minimal reproduction of the bug + assertion that the fix works
- Example: `test_regression_cab_1234.py` for CAB-1234 (auth loop fix)

#### E2E/Playwright Tests
- Tag scenarios with `@regression` for E2E scenarios that verify a bug fix
- Location: `e2e/features/*.feature` file relevant to the component
- Naming: descriptive scenario name that includes the fix scope
- Example scenario in `console-rbac.feature`:
  ```gherkin
  @regression
  Scenario: Fixed — RBAC bypass in API list (CAB-1234)
    Given I am logged in as "viewer"
    When I try to access admin-only APIs
    Then I see only my accessible APIs
  ```

**Regression Guard CI Check** (warning mode): The `regression-guard.yml` workflow detects fix PRs and checks for regression tests. Missing tests trigger a PR annotation (non-blocking).

### Detection
When reviewing a PR, check:
1. Modified files in `src/pages/` → corresponding `.test.tsx` exists?
2. New `vi.mock('AuthContext')` inline → should use `createAuthMock` from helpers?
3. Coverage diff → threshold still met?
4. Commit prefix is `fix()` or PR contains "fix"/"bug" → regression tests present?
5. E2E scenarios for bug fixes → tagged with `@regression`?
