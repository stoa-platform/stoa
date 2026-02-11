---
description: Testing standards across all components
globs: "**/tests/**,**/test_*,**/*.test.*,**/*.spec.*,e2e/**"
---

# Testing Standards

## Python (pytest)
- Framework: pytest + pytest-asyncio (asyncio_mode = "auto")
- Test paths: `tests/`
- File naming: `test_*.py` or `*_test.py`
- Markers: `@slow`, `@integration`, `@unit`
- **Coverage minimum: 70%** (`fail_under = 70`)
- Run: `pytest --cov=src --cov-fail-under=70`

## TypeScript (vitest)
- Framework: **vitest** (NOT Jest) + React Testing Library
- Coverage: v8 provider
- Run: `npm run test` or `npm run test:coverage`

## E2E (Playwright + BDD)
- Location: `e2e/`
- Framework: Playwright + playwright-bdd (Gherkin `.feature` files)
- Test projects: `auth-setup`, `portal-chromium`, `console-chromium`, `gateway`, `ttftc`
- Markers: `@smoke`, `@critical`, `@portal`, `@console`, `@gateway`, `@rpo`
- Auth: persona-based storage states in `fixtures/.auth/`
- Run: `npx playwright test` (from `e2e/`)

## Shared Test Helpers (React)

Both Console and Portal have shared helpers for persona-based testing:
- **Console**: `control-plane-ui/src/test/helpers.tsx`
- **Portal**: `portal/src/test/helpers.tsx`

Key exports: `createAuthMock(role)`, `renderWithProviders(ui, options?)`, mock data factories.
4 personas: `cpi-admin`, `tenant-admin`, `devops`, `viewer`.

See `test-evolution.md` for rules on keeping tests in sync with code changes.

## Rust (cargo test)
- Run: `cargo test` (from `stoa-gateway/`)
