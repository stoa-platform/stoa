# Skill: E2E Test (Playwright BDD)

## Quand utiliser

Quand on demande de creer, modifier ou debugger un test E2E dans `e2e/`.

## Stack

- **Playwright** + **playwright-bdd** (Gherkin)
- TypeScript (ES2022, strict)
- Authentification via Keycloak avec storage states par persona

## Architecture des fichiers

```
e2e/
├── features/<domain>.feature    # Scenarios Gherkin (source de verite)
├── steps/<domain>.steps.ts      # Implementation des steps
├── fixtures/
│   ├── test-base.ts             # Fixtures Playwright custom (URLS, helpers)
│   ├── personas.ts              # Personas + credentials
│   ├── auth.setup.ts            # Auth Keycloak → storage states
│   └── .auth/<persona>.json     # Storage states (gitignored)
├── .features-gen/               # Genere par bddgen (gitignored)
├── playwright.config.ts         # Config: projects, timeouts, reporters
└── package.json                 # Scripts npm
```

## Pipeline: feature → steps → run

1. Ecrire le `.feature` dans `features/`
2. Implementer les steps dans `steps/` (reutiliser les steps existants)
3. `bddgen` genere les specs dans `.features-gen/`
4. Playwright execute les specs generees

## Systeme de personas

Toutes les personas sont definies dans `fixtures/personas.ts`. Theme: Ready Player One.

| Persona    | Tenant    | Role         | defaultApp | Usage typique                    |
|------------|-----------|--------------|------------|----------------------------------|
| `parzival` | high-five | tenant-admin | console    | Admin tenant, tests isolation    |
| `art3mis`  | high-five | devops       | portal     | Tests portal, search, subscribe  |
| `aech`     | high-five | viewer       | portal     | Tests lecture seule              |
| `sorrento` | ioi       | tenant-admin | console    | Tests cross-tenant, isolation    |
| `i-r0k`    | ioi       | viewer       | portal     | Tests lecture tenant concurrent  |
| `anorak`   | * (all)   | cpi-admin    | console    | Tests admin plateforme           |
| `alex`     | oasis     | viewer       | portal     | TTFTC onboarding (fresh, no pre-auth) |

### Credentials

Via `.env` (copier `.env.example`). Format:
```
PARZIVAL_USER=parzival@high-five.io
PARZIVAL_PASSWORD=secret
```

### Auth storage states

`auth.setup.ts` boucle sur toutes les personas, se connecte via Keycloak, sauvegarde le state dans `fixtures/.auth/<persona>.json`.

Les projets Playwright referencent ces states:
```ts
// portal-chromium utilise parzival par defaut
storageState: 'fixtures/.auth/parzival.json',
```

Pour charger une persona dans un step (via `authSession` fixture):
```ts
import { PERSONAS, PersonaKey } from '../fixtures/personas';

// switchPersona() creates a new browser context with storageState
await authSession.switchPersona(personaName as PersonaKey);
// Use authSession.page for subsequent interactions
await authSession.page.goto('/apis');
```

## Projets Playwright

Definis dans `playwright.config.ts`. Chaque projet cible un domaine:

| Projet            | baseURL                  | Auth              | testMatch     |
|-------------------|--------------------------|-------------------|---------------|
| `auth-setup`      | -                        | Keycloak login    | auth.setup.ts |
| `portal-chromium` | `STOA_PORTAL_URL`        | parzival state    | /portal/      |
| `console-chromium`| `STOA_CONSOLE_URL`       | parzival state    | /console/     |
| `gateway`         | `STOA_GATEWAY_URL`       | aucune (API keys) | /gateway/     |
| `ttftc`           | `STOA_PORTAL_URL`        | fresh (alex)      | /alex-ttftc/  |

`auth-setup` est une dependance de portal/console/ttftc (s'execute en premier).

## Tags / Markers

Tags sur les features et scenarios Gherkin. Utilises pour le filtrage.

| Tag          | Usage                                        |
|--------------|----------------------------------------------|
| `@portal`    | Tests Developer Portal                       |
| `@console`   | Tests Console (API Provider)                 |
| `@gateway`   | Tests Gateway API (HTTP, pas de browser)     |
| `@smoke`     | Verification rapide, CI                      |
| `@critical`  | Tests bloquants (isolation, securite)        |
| `@rpo`       | Scenarios demo Ready Player One              |
| `@ttftc`     | Time to First Tool Call (benchmark UX)       |
| `@isolation` | Tests isolation multi-tenant                 |
| `@security`  | Tests securite (cross-tenant, tokens)        |
| `@high-five` | Specifique tenant High-Five                  |
| `@ioi`       | Specifique tenant IOI                        |
| `@filtering` | Tests recherche/filtres                      |
| `@negative`  | Tests de cas d'erreur                        |

Combiner les tags: `@portal @smoke` sur la Feature, `@rpo @high-five` sur le Scenario.

## Commandes

```bash
cd e2e

# Tous les tests
npm run test:e2e

# Par tag
npm run test:smoke
npm run test:critical
npm run test:portal
npm run test:console
npm run test:gateway
npm run test:rpo

# Mode interactif
npm run test:e2e:ui        # UI Playwright
npm run test:e2e:headed    # Navigateur visible
npm run test:e2e:debug     # Mode debug

# Rapport HTML
npm run report
```

## Comment creer un nouveau test

### 1. Feature file

Creer `features/<domain>-<subject>.feature`:

```gherkin
@portal @smoke
Feature: Portal - <Description courte>

  Background:
    Given the STOA Portal is accessible

  @rpo @high-five
  Scenario: <Persona> does <action>
    Given I am logged in as "<persona>" from community "<tenant>"
    When I <action>
    Then I <expected result>
```

Regles:
- Tags Feature = domaine + importance (`@portal @smoke`)
- Tags Scenario = contexte + tenant (`@rpo @high-five`)
- Background pour les preconditions communes
- Steps en anglais (malgre le README qui mentionne le francais, tous les tests existants sont en anglais)
- Nommage fichier: `<domain>-<subject>.feature`

### 2. Step definitions

Ajouter dans le fichier steps existant ou creer `steps/<domain>.steps.ts`:

```ts
/**
 * <Domain> step definitions for STOA E2E Tests
 * <Description>
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// <SECTION NAME>
// ============================================================================

When('I <action with {string} params>', async ({ page }, param: string) => {
  await page.goto(`${URLS.portal}/<path>`);
  await page.waitForLoadState('networkidle');
});

Then('I <assertion>', async ({ page }) => {
  await expect(page.locator('<selector>')).toBeVisible({ timeout: 10000 });
});
```

Regles:
- **Toujours** importer `test` depuis `../fixtures/test-base` (pas depuis `@playwright/test`)
- **Toujours** `createBdd(test)` pour lier les steps aux fixtures custom
- Utiliser `URLS.portal`, `URLS.console`, `URLS.gateway` (pas de URL en dur)
- `page.waitForLoadState('networkidle')` apres chaque navigation
- Timeouts explicites sur les `expect`: `{ timeout: 10000 }`
- Sections separees par `// ====...` avec nom en majuscules
- Reutiliser les steps de `common.steps.ts` avant d'en creer de nouveaux

### 3. Steps existants reutilisables

**common.steps.ts** (auth + navigation):
- `Given I am logged in as {string}` — charge le storage state
- `Given I am logged in as {string} from community {string}` — idem avec contexte tenant
- `Given I am logged in to Console as {string} from team {string}` — Console + navigation
- `Given the STOA Portal is accessible` / `Given the STOA Console is accessible` — health check
- `When I navigate to page {string}` / `When I navigate to the subscriptions page`
- `Then I receive an access denied error`

**portal.steps.ts** (catalog + subscriptions):
- `When I access the API catalog` / `Given I am on the API catalog page`
- `When I search for {string}` / `Then the results contain {string}`
- `When I filter by category {string}`
- `When I click on {string}` — generic button click
- `Then I see APIs in the catalog`
- Steps de subscription (subscribe, confirm, revoke, view key)

**console.steps.ts** (tenant isolation + API management):
- `When I access the API list`
- `Then I see only APIs from tenant {string}` / `Then I do not see APIs from tenant {string}`
- `When I select tenant {string}` / `When I open the tenant selector`
- `When I create an API named {string}`

**gateway.steps.ts** (API calls HTTP):
- `When I call {string}` — format: `"GET /api/v1/path"`
- `Then I receive a {int} response` / `Then I receive a {int} error`
- `Then the error message contains {string}`
- Steps pour API keys (valid, invalid, expired)

### 4. Generer et tester

```bash
cd e2e
npm run bddgen                    # Genere les specs
npx playwright test --grep @<tag> # Run par tag
```

## Exemple concret: portal-catalog.feature

Le test le plus simple du projet:

**Feature** (`features/portal-catalog.feature`):
```gherkin
@portal @smoke
Feature: Portal - API Catalog visibility by community

  Background:
    Given the STOA Portal is accessible

  @rpo @high-five
  Scenario: Parzival sees all public OASIS APIs
    Given I am logged in as "parzival" from community "high-five"
    When I access the API catalog
    Then I see APIs in the catalog
```

**Steps utilises** (deja existants):
- `Given the STOA Portal is accessible` → `common.steps.ts` (line 89)
- `Given I am logged in as {string} from community {string}` → `common.steps.ts` (line 41)
- `When I access the API catalog` → `portal.steps.ts` (line 15)
- `Then I see APIs in the catalog` → `portal.steps.ts` (line 45)

Aucun nouveau step a ecrire. 3 fichiers impliques, 0 code nouveau.

## Patterns a respecter

1. **Pas de `@playwright/test` direct** — toujours passer par `fixtures/test-base.ts`
2. **Pas de selectors fragiles** — preferer `text=`, `role=`, `[class*=]` aux selecteurs CSS specifiques
3. **Pas de `page.waitForTimeout()`** sauf en dernier recours — preferer `waitForLoadState('networkidle')`
4. **Pas de donnees en dur** — les URLs viennent de `URLS`, les credentials de `PERSONAS`
5. **Gateway tests = HTTP pur** — pas de `page`, utiliser `request.fetch()` depuis le fixture
6. **Un fichier steps par domaine** — ne pas melanger portal et console dans le meme fichier
7. **Nommer les features `<domain>-<subject>.feature`** — le `testMatch` des projets Playwright filtre par nom
