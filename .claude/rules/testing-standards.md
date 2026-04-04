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

### Detection Checklist
1. Modified `src/pages/` → corresponding `.test.tsx` exists?
2. New `vi.mock('AuthContext')` inline → should use `createAuthMock`?
3. Coverage diff → threshold still met?
4. PR title `fix(` → regression test present?
5. New test mocks the boundary under test? → redesign per Boundary Integrity Rule

### Evidence Archive Rule (CAB-1969 post-mortem)

Every session that produces Playwright screenshots or test results MUST archive them before ending.
Screenshots are ephemeral — they disappear on `git clean`, branch switch, or next session.

**Archive location**: `audit/<TICKET>/` (gitignored, persists locally).

**Mandatory steps after Playwright runs**:

| Step | Command | Output |
|------|---------|--------|
| 1. Copy screenshots | `find e2e/test-results -name "*.png" -exec cp {} audit/<TICKET>/ \;` | Named PNGs |
| 2. Copy results JSON | `cp e2e/test-results/audit/results.json audit/<TICKET>/` | Machine-readable |
| 3. Copy HTML report | `cp -r e2e/test-results/audit/report audit/<TICKET>/` | Browsable report |
| 4. Write AUDIT-RESULTS.md | See template below | Human-readable summary |
| 5. Update Linear ticket | Post results + screenshot count in ticket description | Traceability |

**AUDIT-RESULTS.md template**:
```markdown
# <TICKET> — Test Results
**Date**: YYYY-MM-DD
**Environment**: Docker Compose / K8s / Prod
**Suite**: `npx playwright test --config <config>`

## Results: X/Y pass (Z skip) — XX.X%
| Phase | Tests | Result | Duration |
|-------|-------|--------|----------|

## Screenshots
| File | What it proves |
|------|----------------|

## How to reproduce
\`\`\`bash
<exact commands>
\`\`\`
```

**Naming convention**: `<Phase>-<description>.png` (e.g., `P1-console-login.png`, `P4-guardrails-devserver.png`).

**When Evidence Pack needed** (audits, RFP, Gartner): run `e2e/scripts/generate-evidence-pack.sh` → self-contained HTML with base64 screenshots. Exclusion A9: no KC admin screenshots, no tokens.
