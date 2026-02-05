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
npm run lint            # eslint (max-warnings 0)
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
