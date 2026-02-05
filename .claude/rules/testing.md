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

## Rust (cargo test)
- Run: `cargo test` (from `stoa-gateway/`)
