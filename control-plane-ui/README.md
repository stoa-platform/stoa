# Console UI (Control Plane)

React admin console for API Providers. Manage tenants, APIs, deployments, subscriptions, gateways, and platform configuration.

## Tech Stack

- React 18.2, TypeScript, Vite
- TanStack React Query 5, Zustand (state), Axios
- react-oidc-context (Keycloak auth), oidc-client-ts
- Tailwind CSS 3.4, Lucide icons
- vitest + React Testing Library

## Prerequisites

- Node.js 20+
- Running Control Plane API
- Keycloak instance (OIDC client: `control-plane-ui`)

## Quick Start

```bash
npm install
cp .env.example .env.local     # Edit VITE_API_URL, VITE_KEYCLOAK_URL
npm start                      # Vite dev server on http://localhost:5173
```

## Commands

```bash
npm start               # Dev server (Vite)
npm run test            # vitest
npm run test:coverage   # vitest with coverage
npm run lint            # eslint (max-warnings 105)
npm run format:check    # prettier
npm run build           # Production build
```

## Project Structure

```
src/
├── main.tsx             # Vite entry point
├── App.tsx              # Root component with routing
├── config.ts            # Keycloak OIDC + service URLs config
├── components/          # Reusable UI components
├── pages/               # Page modules (Tenants, APIs, Deployments, etc.)
├── services/            # API client (api.ts)
├── hooks/               # Custom React hooks
├── contexts/            # Auth/OIDC context
└── types/               # TypeScript type definitions
```

## Configuration

All settings via Vite env vars (`VITE_*` prefix). See `.env.example` for the full list.

Key variables:
- `VITE_API_URL` — Control Plane API base URL
- `VITE_KEYCLOAK_URL` — Keycloak base URL

## Dependencies

- **Depends on**: control-plane-api (REST API), Keycloak (auth)
- **Depended on by**: nothing (end-user UI)
