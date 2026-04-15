# Developer Portal

## Overview
React portal for API Consumers. Browse API catalog, subscribe to APIs, test endpoints, manage API keys, and view documentation.

## Tech Stack
- React 18.2, TypeScript, Vite
- TanStack React Query, Axios
- react-oidc-context (Keycloak auth), oidc-client-ts
- Tailwind CSS, Lucide icons
- vitest + React Testing Library

## Directory Structure
```
src/
├── main.tsx             # Vite entry point
├── App.tsx              # Root component with routing
├── config.ts            # Keycloak OIDC config
├── components/          # 14 component directories
├── pages/               # Pages (Subscriptions, APIs, Tests, Documentation, etc.)
├── services/            # 17 service files (catalog, subscription, integration, etc.)
├── hooks/               # 10+ custom hooks
├── contexts/            # Auth context
├── types/               # TypeScript types
└── utils/               # Helper utilities
```

## Development
```bash
npm install
npm run dev             # Dev server (Vite)
npm run test            # vitest
npm run test:coverage   # vitest with coverage
npm run lint            # eslint (max-warnings 0)
npm run format:check    # prettier
npm run build           # Production build
```

## Differences from Console UI
- Consumer-facing (catalog, subscriptions) vs. Provider-facing (admin, deployments)
- More services (17 vs 7) — richer API integration
- Has `utils/` directory
- Stricter lint threshold (0 warnings vs 105 for Console)
- No Zustand — uses Context/Hooks for state

## Dependencies
- **Depends on**: control-plane-api (REST API), Keycloak (auth)
- **Depended on by**: nothing (end-user UI)

## OIDC Client
- Client ID: `stoa-portal`
- Session storage: `sessionStorage`

## Règles

Détail on-demand: `.claude/docs/code-style-typescript.md`, `testing-standards.md`.

- Prettier: line 100, single quotes, semi, trailing es5, LF.
- ESLint max-warnings: **0**. jsx-a11y plugin actif.
- Components fonctionnels + hooks. React 18 strict. Node 20.
- vitest (PAS Jest). Path alias `@/*` → `src/*`. Build: `tsc -p tsconfig.app.json`.
- Test-Adjacency: nouveau component = tests dans la MÊME PR.
- Helpers-First: `src/test/helpers.tsx` (`createAuthMock`, `renderWithProviders`). Jamais inline mocks.
- `vi.clearAllMocks()` ne reset PAS les implementations. Re-init dans `beforeEach`.
- Boundary Integrity: MSW pour intercept fetch. Jamais mocker la boundary sous test.
- `data-testid` obligatoire. Changement visuel → update goldens MÊME PR.
