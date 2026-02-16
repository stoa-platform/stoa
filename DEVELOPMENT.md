# Development Guide — STOA Platform

One-page guide to get the STOA monorepo running locally.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | `brew install python@3.11` |
| Node.js | 20+ | `brew install node@20` |
| Rust | stable | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| PostgreSQL | 15+ | `brew install postgresql@15` |
| Docker | 24+ | [Docker Desktop](https://docs.docker.com/desktop/) |

Optional (for full stack):
- `librdkafka` — `brew install librdkafka` (gateway Kafka feature)
- `cmake` — `brew install cmake` (required for `cargo test --all-features`)

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/stoa-platform/stoa.git && cd stoa

# 2. Set up all components
make setup

# 3. Start the API (needs PostgreSQL running)
make run-api

# 4. In another terminal, start the Console UI
make run-ui

# 5. In another terminal, start the Gateway
make run-gateway
```

The Console UI is at `http://localhost:5173`, API at `http://localhost:8000`, Gateway at `http://localhost:8080`.

## Component Setup

### Control Plane API (Python)

```bash
cd control-plane-api
pip install -r requirements.txt
cp .env.example .env          # Edit DATABASE_URL, KEYCLOAK_URL
uvicorn src.main:app --reload --port 8000
```

Database setup:
```bash
cd alembic && alembic upgrade head
```

### Console UI (React/TypeScript)

```bash
cd control-plane-ui
npm install
cp .env.example .env.local    # Edit VITE_API_URL, VITE_KEYCLOAK_URL
npm start                     # Vite dev server on :5173
```

### Developer Portal (React/TypeScript)

```bash
cd portal
npm install
cp .env.example .env.local    # Edit VITE_API_URL, VITE_MCP_URL
npm run dev                   # Vite dev server on :5174
```

### STOA Gateway (Rust)

```bash
cd stoa-gateway
cp .env.example .env          # Edit STOA_KEYCLOAK_URL, STOA_CONTROL_PLANE_URL
cargo run                     # Runs on :8080
```

### CLI

```bash
cd cli
pip install -e ".[dev]"
stoa --help
```

## Running Tests

```bash
# All components
make test

# Individual
make test-api       # pytest
make test-ui        # vitest
make test-portal    # vitest
make test-gateway   # cargo test
make test-cli       # pytest
```

## Linting

```bash
# All components
make lint

# Individual
make lint-api       # ruff + black
make lint-ui        # eslint + prettier + tsc
make lint-portal    # eslint + prettier + tsc
make lint-gateway   # clippy + fmt
```

## Environment Variables

Each component has a `.env.example` with all available settings. Required vars for local dev are uncommented; optional vars are commented with defaults shown.

| Component | Config source | Env file |
|-----------|--------------|----------|
| control-plane-api | `src/config.py` | `.env` |
| control-plane-ui | `src/config.ts` | `.env.local` |
| portal | `src/config.ts` | `.env.local` |
| stoa-gateway | `src/config.rs` | `.env` |
| cli | CLI args + OIDC | N/A |

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Browser (localhost)                  │
│   Console (:5173)    Portal (:5174)    Keycloak (:8280) │
└──────────┬──────────────┬────────────────────────────┘
           │              │
           ▼              ▼
┌──────────────────────────────────────────────────────┐
│            Control Plane API (:8000)                  │
│            PostgreSQL (:5432)                          │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│            STOA Gateway (:8080)                       │
│            MCP SSE, Tool Proxy, OAuth 2.1             │
└──────────────────────────────────────────────────────┘
```

## Common Issues

| Problem | Fix |
|---------|-----|
| `cargo test --all-features` fails | Install cmake: `brew install cmake` |
| Keycloak unreachable | Start Keycloak: `docker compose up keycloak -d` |
| Database connection refused | Start PostgreSQL: `brew services start postgresql@15` |
| `npm start` port conflict | Kill process on port: `lsof -ti:5173 \| xargs kill` |
| ESLint max-warnings exceeded | Fix warnings or check threshold in `.eslintrc` |

## Further Reading

- Component READMEs: `control-plane-api/README.md`, `control-plane-ui/README.md`, etc.
- CI quality gates: `.claude/rules/ci-quality-gates.md`
- Git workflow: `.claude/rules/git-workflow.md`
- Architecture decisions: [docs.gostoa.dev/architecture/adr](https://docs.gostoa.dev/docs/architecture/adr)
