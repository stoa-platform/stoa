# Developer Portal

React portal for API Consumers. Browse API catalog, subscribe to APIs, test endpoints, manage API keys, and view documentation.

## Tech Stack

- React 18.2, TypeScript, Vite
- TanStack React Query, Axios
- react-oidc-context (Keycloak auth), oidc-client-ts
- Tailwind CSS, Lucide icons
- vitest + React Testing Library

## Prerequisites

- Node.js 20+
- Running Control Plane API
- Keycloak instance (OIDC client: `stoa-portal`)

## Quick Start

```bash
npm install
cp .env.example .env.local     # Edit VITE_API_URL, VITE_KEYCLOAK_URL
npm run dev                    # Vite dev server on http://localhost:5174
```

## Commands

```bash
npm run dev             # Dev server (Vite)
npm run test            # vitest
npm run test:coverage   # vitest with coverage
npm run lint            # eslint (max-warnings 20)
npm run format:check    # prettier
npm run build           # Production build
```

## Project Structure

```
src/
├── main.tsx             # Vite entry point
├── App.tsx              # Root component with routing
├── config.ts            # Keycloak OIDC + service URLs config
├── components/          # UI components
├── pages/               # Pages (Subscriptions, APIs, Tests, Documentation, etc.)
├── services/            # API client services
├── hooks/               # Custom hooks
├── contexts/            # Auth context
├── types/               # TypeScript types
└── utils/               # Helper utilities
```

## Configuration

All settings via Vite env vars (`VITE_*` prefix). See `.env.example` for the full list.

Key variables:
- `VITE_API_URL` — Control Plane API base URL
- `VITE_MCP_URL` — MCP Gateway base URL
- `VITE_KEYCLOAK_URL` — Keycloak base URL

## Dependencies

- **Depends on**: control-plane-api (REST API), stoa-gateway (MCP API), Keycloak (auth)
- **Depended on by**: nothing (end-user UI)
