# E2E Tests

## Overview
Playwright + BDD end-to-end tests with Gherkin feature files. Covers Portal, Console, Gateway, and TTFTC (Time to First Tool Call) scenarios.

## Tech Stack
- Playwright 1.48, playwright-bdd 7.4, TypeScript
- Gherkin `.feature` files as source of truth

## Test Projects

| Project | Base URL | Auth | Tests |
|---------|----------|------|-------|
| auth-setup | — | Keycloak login | fixtures/auth.setup.ts |
| portal-chromium | STOA_PORTAL_URL | parzival state | features/portal-* |
| console-chromium | STOA_CONSOLE_URL | parzival state | features/console-* |
| gateway | STOA_GATEWAY_URL | API keys | features/gateway-* |
| ttftc | STOA_PORTAL_URL | fresh (alex) | features/alex-ttftc |

## Personas (Ready Player One theme)

| Persona | Tenant | Role | Default App |
|---------|--------|------|-------------|
| parzival | high-five | tenant-admin | console |
| art3mis | high-five | devops | portal |
| aech | high-five | viewer | portal |
| sorrento | ioi | tenant-admin | console |
| i-r0k | ioi | viewer | portal |
| anorak | * (all) | cpi-admin | console |
| alex | oasis | viewer | portal |

## Commands
```bash
npm run test:e2e       # Full suite
npm run test:smoke     # @smoke only
npm run test:critical  # @critical only
npm run test:portal    # @portal only
npm run test:console   # @console only
npm run test:gateway   # @gateway only
npm run test:demo      # @demo only
```

## Dependencies
- **Depends on**: All running services (Portal, Console, API, Gateway, Keycloak)
- See `.claude/skills/e2e-test.md` for detailed patterns and step definitions
