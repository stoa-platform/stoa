# Development Guide — STOA Platform

Local development setup, testing, linting, and troubleshooting for the STOA monorepo.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ (3.12 for `platform/landing-api`) | `brew install python@3.11` |
| Node.js | 20+ | `brew install node@20` |
| Go | 1.26+ (for `stoa-go`) | `brew install go` |
| Rust | stable | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| PostgreSQL | 15+ | `brew install postgresql@15` or use Docker |
| Docker | 24+ (8 GB RAM) | [Docker Desktop](https://docs.docker.com/desktop/) |

Optional (for full stack and Kafka feature tests):
- `librdkafka` — `brew install librdkafka` (gateway Kafka feature)
- `cmake` — `brew install cmake` (required for `cargo test --all-features`)

## Quick Start (Docker Compose)

Run the full platform locally:

```bash
cd deploy/docker-compose
cp .env.example .env
# Set a strong KEYCLOAK_ADMIN_PASSWORD in .env before continuing
docker compose up -d
../../scripts/demo/check-health.sh --wait
```

After startup, sign in to the local Keycloak admin console with `KEYCLOAK_ADMIN` and
`KEYCLOAK_ADMIN_PASSWORD` from `.env`. Create or select a user in the imported
application realm, assign the `cpi-admin` realm role, and set a strong, non-temporary
password. Add the matching username as `ANORAK_USER` and the chosen password as
`ANORAK_PASSWORD` to `.env`.

Load the local configuration into the current shell, then seed demo data:

```bash
set -a
. ./.env
set +a
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

## Quick Start (Individual Components)

```bash
# 1. Clone and enter the repo
git clone https://github.com/stoa-platform/stoa.git && cd stoa

# 2. Install dependencies for all components
make setup

# 3. Start individual services in separate terminals
make run-api        # Control Plane API on :8000 (needs PostgreSQL)
make run-ui         # Console UI on :5173
make run-portal     # Developer Portal on :5174
make run-gateway    # STOA Gateway on :8080
```

## Component Setup

### Control Plane API (Python)

```bash
cd control-plane-api
cp .env.example .env          # Edit DATABASE_URL, KEYCLOAK_URL
pip install -r requirements.txt
(cd alembic && alembic upgrade head)
uvicorn src.main:app --reload --port 8000
```

Key env vars: `DATABASE_URL`, `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`.

### Console UI (React/TypeScript)

```bash
cd control-plane-ui
npm install
cp .env.example .env.local    # Edit VITE_API_URL, VITE_KEYCLOAK_URL
npm run dev                   # Vite dev server on :5173
```

Key env vars: `VITE_API_URL`, `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_CLIENT_ID=control-plane-ui`.

### Developer Portal (React/TypeScript)

```bash
cd portal
npm install
cp .env.example .env.local    # Edit VITE_API_URL, VITE_MCP_URL, VITE_KEYCLOAK_URL
npm run dev                   # Vite dev server on :5174
```

Key env vars: `VITE_API_URL`, `VITE_MCP_URL`, `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_CLIENT_ID=stoa-portal`.

### STOA Gateway (Rust)

```bash
cd stoa-gateway
cp .env.example .env          # Edit STOA_KEYCLOAK_URL, STOA_CONTROL_PLANE_URL
cargo run                     # Runs on :8080
```

Key env vars: `STOA_KEYCLOAK_URL`, `STOA_KEYCLOAK_REALM`, `STOA_CONTROL_PLANE_URL`, `STOA_GATEWAY_MODE=edge-mcp`.

### CLI (`stoactl`, Go)

The official STOA CLI lives in `stoa-go/` (the `cli/` directory contains only legacy Python CLI documentation):

```bash
go -C stoa-go build -o stoactl ./cmd/stoactl
./stoa-go/stoactl --help
```

### E2E Tests

Requires running services (Docker Compose or individual components):

```bash
cd e2e
npm install
npx playwright install chromium
cp .env.example .env
npm run test:smoke            # Quick smoke tests
npm run test:e2e              # Full suite
npm run test:e2e:ui           # Interactive UI mode
```

## Running Tests

```bash
# All components
make test

# Individual
make test-api                 # pytest (70% coverage required)
make test-ui                  # vitest
make test-portal              # vitest
make test-gateway             # cargo test
make test-gateway-all-features # cargo test --all-features (requires cmake + librdkafka)
make test-cli                 # go test in stoa-go
```

## Linting

```bash
# All components
make lint

# Individual
make lint-api                 # ruff + black
make lint-ui                  # eslint (--max-warnings 110) + prettier + tsc
make lint-portal              # eslint (--max-warnings 0) + prettier + tsc
make lint-gateway             # clippy (-D warnings) + cargo fmt --check
make lint-cli                 # go vet in stoa-go
```

## Database Migrations

```bash
cd control-plane-api/alembic
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Environment Variables

Each component has a `.env.example` with all available settings. Required vars for local dev are uncommented; optional vars are commented with defaults shown.

| Component | Config source | Env file |
|-----------|--------------|----------|
| `control-plane-api` | `src/config.py` | `.env` |
| `control-plane-ui` | `src/config.ts` | `.env.local` |
| `portal` | `src/config.ts` | `.env.local` |
| `stoa-gateway` | `src/config.rs` | `.env` |
| `stoa-go` (`stoactl`) | `~/.stoa/config` + OIDC | N/A |

## Architecture

```text
┌────────────────────────────────────────────────────────┐
│                   Browser (localhost)                  │
│   Console (:5173)    Portal (:5174)    Keycloak (:8280)│
└──────────┬──────────────┬──────────────────────────────┘
           │              │
           ▼              ▼
┌────────────────────────────────────────────────────────┐
│            Control Plane API (:8000)                   │
│            PostgreSQL (:5432)                          │
└──────────────────────┬─────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────┐
│            STOA Gateway (:8080)                        │
│            MCP, Tool Proxy, OAuth 2.1                  │
└────────────────────────────────────────────────────────┘
```

## Git Workflow and CI Checks

- **Branch naming**: `feat/issue-123-description`, `fix/issue-456-description`
- **Commit format**: `type(scope): description` (commitlint enforced)
- **Signed commits & DCO**: sign commits (`git commit -S -s`); see [CONTRIBUTING.md](CONTRIBUTING.md)
- **Merge strategy**: squash merge via pull request; component CI runs on touched paths via `.github/workflows/ci-gate.yml`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Port conflict on `:80` | Edit `deploy/docker-compose/.env` to change port mappings |
| Port conflict on `:5173` | Kill process on port: `lsof -ti:5173 \| xargs kill` |
| Keycloak slow to start | Normal (60-90s), loads imported realms |
| Keycloak unreachable | Start Keycloak: `docker compose up keycloak -d` |
| Database connection refused | Start PostgreSQL: `brew services start postgresql@15` |
| `cargo test --all-features` fails | Install cmake: `brew install cmake` |
| OpenSearch won't start (Linux) | `sudo sysctl -w vm.max_map_count=262144` |
| Console lint fails | Threshold is `--max-warnings 110` (see `control-plane-ui/package.json`) |
| Portal lint fails | Threshold is `--max-warnings 0` (stricter than Console) |

## Further Reading

- Contributor onboarding: [docs/contributing/getting-started.md](docs/contributing/getting-started.md)
- Component READMEs: `control-plane-api/README.md`, `control-plane-ui/README.md`, `portal/README.md`, `stoa-gateway/README.md`, `stoa-go/README.md`
- CI pipeline: [.github/workflows/](.github/workflows/)
- Conventions and AI usage policy: [CONTRIBUTING.md](CONTRIBUTING.md)
- Platform overview: [docs/platform.md](docs/platform.md)
- Architecture decisions: [docs.gostoa.dev/docs/architecture/adr](https://docs.gostoa.dev/docs/architecture/adr)
