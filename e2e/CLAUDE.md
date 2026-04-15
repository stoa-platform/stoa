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

## Règles

Détail on-demand: `.claude/docs/e2e-audit.md`, `testing-standards.md`.

- Audits → `docs/audits/YYYY-MM-DD-<topic>/` avec README.md + report/index.html + results.json.
- Pas de skips. Si blocage → fix le blocker, pas le test.
- Pas de fake data. Toute valeur affichée dans un dashboard vient d'une action phase précédente.
- Screenshots = assertions. `fullPage: true`, naming `trace-<app>-<page>.png`.
- Cross-validation obligatoire: Phase D query l'API et assert counts == actions phases précédentes.
- Idempotent: tests runnable N fois sans cleanup. Timestamps dans names, handle 409.
- `@regression` tag sur scénarios bloquant des fixes (regression-guard.yml).
- Feature/fix ticket MUST update Playwright scenarios dans la MÊME PR. Pas de "test later".
- Evidence archive après CHAQUE run: `docs/audits/<date>-<topic>/`. Pas d'archive = session incomplète.
- `data-testid` convention: `<section>-<element>[-<variant>]`. Suffixes `-count`/`-timestamp`/`-duration` auto-masked.
- axe-core threshold: `critical` (WCAG 2.1 AA). Nouvelle page Console → ajouter à `CONSOLE_PAGES`.
- Visual regression: golden baselines dans `e2e/golden/`. Regen via Docker (voir docs).
