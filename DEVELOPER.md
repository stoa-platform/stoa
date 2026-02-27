# Developer Guide

Local development setup for the STOA Platform monorepo.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ (3.12 for landing-api) | `brew install python@3.11` |
| Node.js | 20+ | `brew install node@20` |
| Rust | stable | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Docker | 4.x+ (8 GB RAM) | [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| PostgreSQL | 15+ | `brew install postgresql@15` or use Docker |
| librdkafka | latest (optional) | `brew install librdkafka` |
| cmake | latest (optional) | `brew install cmake` |

## Quick Start (Docker Compose)

The fastest way to run the full platform locally:

```bash
cd deploy/docker-compose
cp .env.example .env
docker compose up -d
../../scripts/demo/check-health.sh --wait
../../scripts/demo/seed-all.sh --skip-traffic
```

Access points (via nginx on port 80):

| Service | URL | Direct Port |
|---------|-----|-------------|
| Console | http://localhost | 3000 |
| Portal | http://localhost/portal | 3002 |
| API Docs | http://localhost/api/docs | 8000 |
| Keycloak | http://localhost/auth | 8080 |
| Grafana | http://localhost/grafana | 3001 |
| Gateway | http://localhost/gateway/health | 8081 |

Demo credentials:

| User | Password | Role |
|------|----------|------|
| halliday | readyplayerone | Platform Admin |
| parzival | copperkeystart | Tenant Admin |
| art3mis | samantha2045 | DevOps |
| aech | helen2045 | Viewer |

## Quick Start (Individual Components)

Use `make` targets for convenience:

```bash
make setup          # Install deps for all components
make run-api        # API on :8000
make run-ui         # Console on :5173
make run-portal     # Portal on :5174
make run-gateway    # Gateway on :8080
```

Or run components manually -- see sections below.

## Components

### Control Plane API

```bash
cd control-plane-api
cp .env.example .env          # Set DATABASE_URL, KEYCLOAK_URL
pip install -r requirements.txt
cd alembic && alembic upgrade head && cd ..
uvicorn src.main:app --reload --port 8000
```

Key env vars: `DATABASE_URL`, `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`

### Console UI

```bash
cd control-plane-ui
npm install
cp .env.example .env.local    # Set VITE_API_URL, VITE_KEYCLOAK_URL
npm start
```

Key env vars: `VITE_API_URL`, `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_CLIENT_ID=control-plane-ui`

### Portal

```bash
cd portal
npm install
cp .env.example .env.local    # Set VITE_API_URL, VITE_MCP_URL, VITE_KEYCLOAK_URL
npm run dev
```

Key env vars: `VITE_API_URL`, `VITE_MCP_URL`, `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_CLIENT_ID=stoa-portal`

### STOA Gateway

```bash
cd stoa-gateway
cp .env.example .env          # Set STOA_KEYCLOAK_URL, STOA_CONTROL_PLANE_URL
cargo run
```

Key env vars: `STOA_KEYCLOAK_URL`, `STOA_KEYCLOAK_REALM`, `STOA_CONTROL_PLANE_URL`, `STOA_GATEWAY_MODE=edge-mcp`

### CLI

```bash
cd cli
pip install -e ".[dev]"
stoa --help
```

### E2E Tests

Requires running services (Docker Compose or individual components).

```bash
cd e2e
npm install
npx playwright install chromium
cp .env.example .env
npm run test:smoke            # Quick smoke tests
npm run test:e2e              # Full suite
npm run test:e2e:ui           # Interactive UI mode
```

## Testing

### Run All Tests

```bash
make test
```

### Per-Component

```bash
# Python (control-plane-api) -- 70% coverage required
cd control-plane-api
pytest tests/ --cov=src --cov-fail-under=70 --ignore=tests/test_opensearch.py -q

# TypeScript (console) -- max-warnings: 105
cd control-plane-ui
npm run test -- --run

# TypeScript (portal) -- max-warnings: 0
cd portal
npm run test -- --run

# Rust (gateway) -- zero warnings
cd stoa-gateway
cargo test
cargo test --all-features     # Requires cmake + librdkafka
```

## Linting

### Run All Linters

```bash
make lint
```

### Per-Component

```bash
# Python
cd control-plane-api
ruff check . && black --check .

# Console
cd control-plane-ui
npm run lint && npm run format:check && npx tsc -p tsconfig.app.json --noEmit

# Portal
cd portal
npm run lint && npm run format:check && npx tsc -p tsconfig.app.json --noEmit

# Rust
cd stoa-gateway
cargo fmt --check
RUSTFLAGS=-Dwarnings cargo clippy --all-targets --all-features -- -D warnings
```

## Database Migrations

```bash
cd control-plane-api/alembic
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Git Workflow

- **Branch naming**: `feat/issue-123-description`, `fix/issue-456-description`
- **Commit format**: `type(scope): description` (commitlint enforced)
- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`
- **Scopes**: `api`, `ui`, `portal`, `gateway`, `helm`, `ci`, `docs`, `deps`
- **Merge strategy**: always squash merge via PR
- **Signed commits**: required by branch protection

## CI Required Checks

Every PR must pass these 3 checks before merge:

1. **License Compliance** -- Trivy SPDX scan
2. **SBOM Generation** -- CycloneDX + SPDX
3. **Verify Signed Commits** -- signature check

Component-specific CI runs only when relevant paths change.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Port conflict on :80 | Edit `deploy/docker-compose/.env` to change port mappings |
| Keycloak slow to start | Normal (60-90s), loads 6 realms |
| `cargo test --all-features` fails | Install cmake: `brew install cmake` |
| OpenSearch won't start (Linux) | `sudo sysctl -w vm.max_map_count=262144` |
| Console lint fails | Max-warnings is 105, not 0 -- check `package.json` |
| Portal lint fails | Max-warnings is 0 (stricter than Console) |
