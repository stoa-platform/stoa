# STOA E2E Tests

Tests end-to-end (E2E) pour la plateforme STOA utilisant **Playwright** et **Gherkin (BDD)**.

## Stack Technique

- **Playwright** - Framework de test browser automation
- **playwright-bdd** - Integration Gherkin/Cucumber pour Playwright
- **TypeScript** - Typage statique
- **Gherkin (FR)** - Scenarios BDD en francais

## Structure

```
e2e/
├── features/                    # Fichiers Gherkin (.feature)
│   ├── portal-catalog.feature
│   ├── console-isolation.feature
│   ├── subscription-workflow.feature
│   └── gateway-access-control.feature
├── steps/                       # Step definitions
│   ├── common.steps.ts
│   ├── portal.steps.ts
│   ├── console.steps.ts
│   └── gateway.steps.ts
├── fixtures/                    # Fixtures et auth
│   ├── personas.ts
│   ├── auth.setup.ts
│   └── .auth/                   # Storage states (gitignored)
├── playwright.config.ts         # Configuration Playwright
├── package.json
└── tsconfig.json
```

## Personas (Ready Player One)

| Persona | Tenant | Role | Description |
|---------|--------|------|-------------|
| parzival | high-five | tenant-admin | CPI High-Five |
| art3mis | high-five | devops | DevOps High-Five |
| aech | high-five | viewer | Viewer High-Five |
| sorrento | ioi | tenant-admin | CPI IOI |
| i-r0k | ioi | viewer | Viewer IOI |
| anorak | * | cpi-admin | Platform Admin |

## Installation

```bash
cd e2e
npm install
npx playwright install chromium
```

## Configuration

1. Copier `.env.example` vers `.env`
2. Remplir les credentials des personas

```bash
cp .env.example .env
# Editer .env avec les mots de passe
```

## Commandes

```bash
# Generer et lancer tous les tests
npm run test:e2e

# Tests par tag
npm run test:smoke       # Tests smoke
npm run test:critical    # Tests critiques (isolation)
npm run test:portal      # Tests Portal uniquement
npm run test:console     # Tests Console uniquement
npm run test:rpo         # Scenarios Ready Player One

# Mode interactif
npm run test:e2e:ui      # UI mode Playwright
npm run test:e2e:headed  # Avec navigateur visible
npm run test:e2e:debug   # Mode debug

# Voir le rapport
npm run report
```

## Tags Gherkin

- `@portal` - Tests du Developer Portal
- `@console` - Tests de la Console (API Provider)
- `@gateway` - Tests du Gateway API
- `@smoke` - Tests rapides de verification
- `@critical` - Tests critiques (bloquants)
- `@isolation` - Tests d'isolation multi-tenant
- `@rpo` - Scenarios demo Ready Player One
- `@high-five` - Scenarios tenant High-Five
- `@ioi` - Scenarios tenant IOI

## Ecrire des Tests

### Feature File (Gherkin FR)

```gherkin
# language: fr
@portal @smoke
Fonctionnalite: Catalogue des APIs

  Scenario: Voir le catalogue
    Etant donne que je suis connecte en tant que "art3mis"
    Quand je navigue vers la page "/apis"
    Alors je dois voir le titre "API Catalog"
```

### Step Definition

```typescript
import { createBdd } from 'playwright-bdd';
import { test } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

Given('que je suis connecte en tant que {string}', async ({ page }, persona) => {
  // Implementation
});
```

## CI/CD

Les tests sont executes automatiquement via GitHub Actions:
- Sur push vers `main` ou `develop`
- Sur pull requests
- Manuellement via workflow dispatch

## Liens

- [Playwright Documentation](https://playwright.dev/)
- [playwright-bdd](https://github.com/vitalets/playwright-bdd)
- [Gherkin Reference (FR)](https://cucumber.io/docs/gherkin/reference/)
