CAB-1103 Phase 6C: E2E Expansion — 20+ nouveaux scenarios Playwright BDD.

Branch: `feat/cab-1103-6c-e2e-expansion` (creer depuis main)

## Contexte
81 scenarios E2E existent (PR #175). 100% route coverage (Console 26/26, Portal 16/16).
Il manque les scenarios fonctionnels: Gateway CRUD, deployment lifecycle, RBAC admin, portal consumer flow.

## Architecture E2E existante
```
e2e/
├── features/           # Fichiers .feature (Gherkin)
│   ├── console/        # Scenarios Console UI
│   └── portal/         # Scenarios Portal
├── steps/              # Step definitions
├── fixtures/           # Auth fixtures (storageState)
│   └── .auth/          # Fichiers auth JSON par persona
├── playwright.config.ts
└── package.json
```

Personas disponibles (storageState pattern):
- `parzival` = cpi-admin (stoa:admin)
- `sorrento` = tenant-admin (stoa:write, stoa:read) — verifier si existe, sinon creer le fixture
- `art3mis` = viewer (stoa:read) — verifier si existe, sinon creer le fixture

## Taches

### 1. Explorer l'existant
- Lire `e2e/features/console/` et `e2e/features/portal/` pour comprendre les patterns
- Lire `e2e/fixtures/` pour les auth fixtures
- Lire `e2e/playwright.config.ts` pour les projects et la config BDD
- Lire `e2e/steps/` pour les step definitions existantes

### 2. Gateway CRUD (~6 scenarios)
Fichier: `e2e/features/console/gateway-crud.feature`

```gherkin
Feature: Gateway CRUD
  As a platform admin
  I want to manage gateway instances
  So that I can control the data plane

  @console @gateway
  Scenario: Admin creates a new gateway instance
  Scenario: Admin lists all gateway instances
  Scenario: Admin views gateway details with status badge
  Scenario: Admin updates gateway configuration
  Scenario: Admin deletes a gateway instance
  Scenario: Viewer cannot create or delete gateways
```

### 3. Deployment Lifecycle (~5 scenarios)
Fichier: `e2e/features/console/deployment-lifecycle.feature`

```gherkin
Feature: Deployment Lifecycle
  As a devops user
  I want to deploy APIs to gateways
  So that they are available to consumers

  @console @deployment
  Scenario: Deploy an API to a gateway
  Scenario: Verify deployment appears in gateway details
  Scenario: Verify sync status is SYNCED
  Scenario: Undeploy an API from a gateway
  Scenario: Deployment list shows correct status badges
```

### 4. Admin RBAC (~5 scenarios)
Fichier: `e2e/features/console/admin-rbac.feature`

```gherkin
Feature: Admin RBAC
  As different role users
  I want appropriate access to console features
  So that the platform is secure

  @console @rbac
  Scenario: Admin (parzival) sees all menu items
  Scenario: Tenant admin (sorrento) sees limited menu
  Scenario: Viewer (art3mis) sees read-only interface
  Scenario: Viewer cannot access admin pages
  Scenario: Tenant admin cannot modify other tenants
```

### 5. Portal Consumer Flow (~6 scenarios)
Fichier: `e2e/features/portal/consumer-flow.feature`

```gherkin
Feature: Portal Consumer Flow
  As a developer
  I want to discover and subscribe to APIs
  So that I can integrate them in my applications

  @portal @consumer
  Scenario: Browse API catalog
  Scenario: View API details and documentation
  Scenario: Subscribe to an API
  Scenario: View subscription with API key
  Scenario: Select gateway for subscription
  Scenario: Revoke a subscription
```

### 6. Creer les step definitions
- `e2e/steps/gateway-crud.steps.ts`
- `e2e/steps/deployment-lifecycle.steps.ts`
- `e2e/steps/admin-rbac.steps.ts`
- `e2e/steps/consumer-flow.steps.ts`

Suivre le pattern existant: `Given/When/Then` avec `page.goto()`, `page.click()`, `expect(page.locator(...))`.
Utiliser les soft assertions (`expect.soft()`) — documenter les frictions, ne jamais bloquer.

### 7. Verifier
- `npx playwright test --list` doit montrer >= 20 nouveaux scenarios
- Les features sont syntaxiquement correctes
- Les steps sont implementes (meme si certains utilisent `test.skip` pour les fonctionnalites non encore deployees)

## DoD
- [ ] >= 20 nouveaux scenarios Playwright BDD
- [ ] 4 fichiers .feature (gateway-crud, deployment-lifecycle, admin-rbac, consumer-flow)
- [ ] 4 fichiers step definitions correspondants
- [ ] Auth fixtures pour sorrento et art3mis si manquants
- [ ] Commit: `test(e2e): add 22 gateway/deployment/RBAC/consumer scenarios (CAB-1103)`

## Contraintes
- Utiliser le pattern BDD existant (playwright-bdd + Gherkin)
- Utiliser storageState pour l'auth (pas de login dans les tests)
- Soft assertions partout (`expect.soft()`)
- Marquer `@wip` les scenarios qui dependent de features non deployees
- Ne PAS push
