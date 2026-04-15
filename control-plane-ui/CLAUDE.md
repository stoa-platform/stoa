# Console UI (Control Plane)

## Overview
React admin console for API Providers. Manage tenants, APIs, deployments, subscriptions, gateways, and platform configuration.

## Tech Stack
- React 18.2, TypeScript, Vite
- TanStack React Query 5, Zustand (state), Axios
- react-oidc-context (Keycloak auth), oidc-client-ts
- Tailwind CSS 3.4, Lucide icons
- vitest + React Testing Library

## Directory Structure
```
src/
├── main.tsx             # Vite entry point
├── App.tsx              # Root component with routing
├── config.ts            # Keycloak OIDC config
├── components/          # Reusable UI components (Layout, SyncStatusBadge, etc.)
├── pages/               # Page modules (Tenants, APIs, Deployments, Gateways, etc.)
├── services/            # API client (api.ts)
├── hooks/               # Custom React hooks
├── contexts/            # Auth/OIDC context
└── types/               # TypeScript type definitions
```

## Development
```bash
npm install
npm start               # Dev server (Vite)
npm run test            # vitest
npm run lint            # eslint (max-warnings 100)
npm run format:check    # prettier
npm run build           # Production build
```

## Key Patterns
- Functional components + hooks only
- Keycloak OIDC via react-oidc-context
- TanStack Query for server state
- Zustand for client state
- Path alias: `@/*` maps to `src/*`

## Dependencies
- **Depends on**: control-plane-api (REST API), Keycloak (auth)
- **Depended on by**: nothing (end-user UI)

## OIDC Client
- Client ID: `control-plane-ui`
- Session storage: `sessionStorage` (not localStorage)

## Règles

Détail on-demand: `.claude/docs/code-style-typescript.md`, `testing-standards.md`.

- Prettier: line 100, single quotes, semi, trailing es5, LF.
- ESLint max-warnings: 100 (ratchet, jamais augmenter).
- Components fonctionnels + hooks. Pas de classes. React 18 strict. Node 20.
- vitest (PAS Jest). Path alias `@/*` → `src/*`.
- `tsconfig.app.json` exclut `**/*.test.ts(x)`. Build: `tsc -p tsconfig.app.json`.
- Persona Rule: composants RBAC-conditional testés pour les 4 personas (cpi-admin, tenant-admin, devops, viewer).
- Helpers-First: utiliser `src/test/helpers.tsx` (`createAuthMock`, `renderWithProviders`). Jamais inline `vi.mock('AuthContext')`.
- `vi.clearAllMocks()` ne reset PAS les implementations. Re-init dans `beforeEach`.
- Boundary Integrity: MSW pour intercept fetch, pas 8 `vi.mock()` + `getByText('Dashboard')`.
- `data-testid` obligatoire sur nouveaux components. Convention `<section>-<element>[-<variant>]`.
- Changement visuel UI → update golden baselines dans la MÊME PR.
