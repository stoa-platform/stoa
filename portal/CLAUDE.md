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
