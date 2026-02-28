---
globs: "control-plane-ui/**,portal/**"
---

# TypeScript / React Code Style

## Tools: eslint + prettier

## Prettier
- Line length: 100
- Semicolons: yes
- Quotes: single
- Trailing commas: es5
- End of line: LF

## ESLint
- Max warnings: 105 (control-plane-ui), 0 (portal)
- Path alias: `@/*` maps to `src/*`
- Unused args: prefix with `_` (e.g., `_unused`)

## Run
```bash
npm run lint && npm run format:check
```

## Conventions
- Functional components + hooks (no class components)
- React 18, TypeScript strict
- Keycloak-js for auth
- vitest (NOT Jest) for testing
- Node 20 required
