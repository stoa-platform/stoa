<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
globs: "stoa-gateway/**,control-plane-api/**,control-plane-ui/**,portal/**,e2e/**"
description: Context7 MCP usage patterns for up-to-date library documentation
---
# Context7 — Library Documentation Lookup

## When to Use

Use Context7 MCP to fetch **up-to-date docs** instead of relying on training data, especially for:
- API changes between versions (axum 0.7→0.8, FastAPI 0.100+, Keycloak 26+)
- New features not in training data
- Correct usage patterns when unsure

## Workflow

```
1. mcp__context7__resolve-library-id("library name") → get library ID
2. mcp__context7__query-docs(libraryId, topic) → get current docs
```

## Key Libraries

| Library | When to Lookup | Example Topics |
|---------|---------------|----------------|
| `tokio-rs/axum` | Router, middleware, State, extractors | "Router::new layer middleware ordering" |
| `tiangolo/fastapi` | Dependencies, middleware, lifespan | "Depends injection async" |
| `keycloak/keycloak` | Admin API, realm config, OIDC | "admin REST API create client" |
| `playwright` | Locators, assertions, BDD | "locator.filter has-text" |
| `vitejs/vite` | Config, plugins, env | "vite config proxy" |
| `vitest-dev/vitest` | Mocking, setup, config | "vi.mock module" |
| `sqlalchemy` | Async session, relationships | "async_sessionmaker select" |

## Rules

- **Lookup before guessing** — if you're unsure about an API signature, query Context7
- **Cache mentally** — once you've fetched docs for a topic in a session, don't re-fetch
- **Specific topics** — "axum middleware ordering" is better than "axum" (more relevant results)
- **Write down key info** — tool results may be cleared from context; note important findings
