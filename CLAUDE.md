# CLAUDE.md - Instructions for Claude Code

## Project Overview
STOA Platform v2 - Multi-tenant API Management with:
- UI RBAC Control-Plane (React + Keycloak)
- MCP Gateway for AI-Native API Access
- GitOps (GitLab as Source of Truth)
- Event-Driven Architecture (Kafka/Redpanda)
- AWX Automation

## CRITICAL RULES - DO NOT VIOLATE

### Infrastructure Protection
- **NEVER run `terraform destroy`** without explicit user confirmation
- **NEVER delete EKS clusters** in production
- **NEVER delete GitLab repositories** with production data
- **NEVER delete Kafka topics** with unprocessed events
- **NEVER modify Keycloak realm** without backup

### Safe Operations
- `terraform plan` - Always run before apply
- `helm diff` - Preview Helm changes
- `kubectl get` - Read-only operations
- `git status/log` - Git read operations

### Docker Build Requirements
- **ALWAYS build multi-arch images** for both AMD64 and ARM64
- EKS runs on AMD64 (linux/amd64), local Mac uses ARM64
- Use `docker buildx build --platform linux/amd64,linux/arm64` for all image builds
- Example: `docker buildx build --platform linux/amd64,linux/arm64 -t <image> --push .`

## Architecture

### Components
- **control-plane-ui/**: Console UI (React) - API Provider interface for tenant/API management
- **portal/**: Developer Portal (React + Vite) - API Consumer portal for browse, subscribe, test APIs
- **control-plane-api/**: FastAPI backend with Keycloak auth
- **mcp-gateway/**: STOA Gateway (edge-mcp mode) - AI-Native API access via MCP protocol
- **stoa-gateway/**: STOA Gateway (Rust) - Emerging implementation for all 4 modes
- **charts/stoa-platform/**: Helm chart for K8s deployment
- **terraform/**: AWS infrastructure (EKS, RDS, etc.)

### STOA Gateway (Unified Architecture - ADR-024)

The gateway component implements 4 deployment modes under a unified architecture:
- **edge-mcp** (current): MCP protocol, SSE, tools/call - Python implementation in `mcp-gateway/`
- **sidecar** (planned Q2): Behind 3rd-party gateways (Kong, Envoy, Apigee)
- **proxy** (planned Q3): Inline policy enforcement, rate limiting
- **shadow** (deferred): Passive traffic capture, UAC auto-generation

See [ADR-024](https://docs.gostoa.dev/architecture/adr/adr-024-gateway-unified-modes) for the full architecture decision.

**Current**: Python/FastAPI (`mcp-gateway/`) - production
**Target**: Rust/Tokio (`stoa-gateway/`) - Q4 2026

### Edge-MCP Mode Features (Phase 12)
- **Tool Registry**: Dynamic tool registration from CRDs
- **OPA Policy Engine**: Fine-grained RBAC (CAB-122)
- **Metering Pipeline**: Kafka-based usage tracking (CAB-123)
- **Kubernetes CRDs**: Tool and ToolSet resources (CAB-121)

### Key Technologies
- **Frontend**: React 18, TypeScript, Keycloak-js
- **Backend**: FastAPI, Python 3.11, aiokafka
- **MCP Gateway**: FastAPI, OPA (embedded), Kubernetes CRDs
- **Infrastructure**: EKS, RDS PostgreSQL, ALB
- **Event Streaming**: Redpanda (Kafka-compatible)
- **Auth**: Keycloak (OIDC)
- **GitOps**: GitLab + ArgoCD
- **Automation**: AWX (Ansible Tower)

### RBAC Roles
1. **cpi-admin**: Full platform access (stoa:admin scope)
2. **tenant-admin**: Manage own tenant (stoa:write, stoa:read)
3. **devops**: Deploy and promote APIs (stoa:write, stoa:read)
4. **viewer**: Read-only access (stoa:read)

## Common Tasks

### Development
```bash
# Console UI Development (API Provider)
cd control-plane-ui && npm install && npm start

# Developer Portal Development (API Consumer)
cd portal && npm install && npm run dev

# API Development
cd control-plane-api && pip install -r requirements.txt && uvicorn src.main:app --reload

# MCP Gateway Development
cd mcp-gateway && pip install -e ".[dev,k8s]" && python -m src.main

# Run MCP Gateway tests
cd mcp-gateway && pytest --cov=src

# Run Portal tests
cd portal && npm run test

# Helm lint
helm lint charts/stoa-platform
```

### Deployment
```bash
# Terraform
cd terraform/environments/dev
terraform init && terraform plan && terraform apply

# Helm (includes MCP Gateway)
helm upgrade --install stoa-platform ./charts/stoa-platform -n stoa-system --create-namespace

# Apply CRDs
kubectl apply -f charts/stoa-platform/crds/
```

### MCP Gateway
```bash
# Register a tool via CRD
kubectl apply -f - <<EOF
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: my-api-tool
  namespace: tenant-acme
spec:
  displayName: My API Tool
  description: A sample tool
  endpoint: https://api.example.com/v1/action
  method: POST
EOF

# Check tool status
kubectl get tools -n tenant-acme
```

## Key URLs (Production)
- Console UI: https://console.gostoa.dev (API Provider)
- **Developer Portal**: https://portal.gostoa.dev (API Consumer)
- **Control-Plane-API**: https://api.gostoa.dev (used by Console UI & Portal)
- API Gateway Runtime: https://apis.gostoa.dev (for external API consumers)
- Gateway Admin: https://gateway.gostoa.dev
- MCP Gateway: https://mcp.gostoa.dev
- Keycloak: https://auth.gostoa.dev
- AWX: https://awx.gostoa.dev
- ArgoCD: https://argocd.gostoa.dev
- Vault: https://vault.gostoa.dev

## Configuration
The platform uses `BASE_DOMAIN` as single source of truth for all URLs.
See `deploy/config/{dev,staging,prod}.env` for environment-specific configuration.

### MCP Gateway Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `OPA_ENABLED` | `true` | Enable OPA policy engine |
| `OPA_EMBEDDED` | `true` | Use embedded evaluator |
| `METERING_ENABLED` | `true` | Enable Kafka metering |
| `K8S_WATCHER_ENABLED` | `false` | Enable CRD watcher |

## Runtime Versions

| Tool   | Version | Notes                          |
|--------|---------|--------------------------------|
| Python | 3.11    | control-plane-api, mcp-gateway |
| Python | 3.12    | landing-api                    |
| Node   | 20      | portal, control-plane-ui       |

## Code Style

### Python (ruff + black + isort)
- **Line length**: 100 (mcp-gateway, landing-api), 120 (control-plane-api)
- **Ruff rules**: E, W, F, I, B, C4, UP, ARG, SIM, S, DTZ, LOG, RUF
- **Type checking**: mypy with `disallow_untyped_defs = true`
- **First-party package**: `src`
- Run: `ruff check . && black --check . && mypy src/`

### TypeScript / React (eslint + prettier)
- **Line length**: 100
- **Prettier**: semicolons, single quotes, trailing commas (es5), LF
- **Path alias**: `@/*` maps to `src/*`
- **Unused args**: prefix with `_` (e.g., `_unused`)
- **Max warnings**: 0 (control-plane-ui), 20 (portal)
- Run: `npm run lint && npm run format:check`

## Testing Standards

### Python (pytest)
- Framework: pytest + pytest-asyncio (asyncio_mode = "auto")
- Test paths: `tests/`
- File naming: `test_*.py` or `*_test.py`
- Markers: `@slow`, `@integration`, `@unit`
- **Coverage minimum: 70%** (`fail_under = 70`)
- Run: `pytest --cov=src --cov-fail-under=70`

### TypeScript (vitest)
- Framework: **vitest** (NOT Jest) + React Testing Library
- Coverage: v8 provider
- Run: `npm run test` or `npm run test:coverage`

### E2E (Playwright + BDD)
- Location: `e2e/`
- Framework: Playwright + playwright-bdd (Gherkin `.feature` files)
- Test projects: `auth-setup`, `portal-chromium`, `console-chromium`, `gateway`, `ttftc`
- Markers: `@smoke`, `@critical`, `@portal`, `@console`, `@gateway`, `@rpo`
- Auth: persona-based storage states in `fixtures/.auth/`
- Run: `npx playwright test` (from `e2e/`)

## Commit & Branch Conventions

### Commit Messages (commitlint enforced via husky)
- Format: `<type>(<scope>): <subject>` (max 72 chars subject, 100 chars header)
- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`
- **Scopes**: `api`, `ui`, `portal`, `mcp`, `gateway`, `helm`, `ci`, `docs`, `deps`, `security`, `demo`
- Example: `fix(api): escape LIKE wildcards in portal search (CAB-1044)`

### Branch Naming
- `feat/<ticket-id>-<description>` for new features
- `fix/<ticket-id>-<description>` for bug fixes
- Example: `fix/cab-1044-search-escape`

## Project Structure

```
stoa/
├── control-plane-api/     # FastAPI backend (Python 3.11)
├── control-plane-ui/      # Console UI - API Provider (React/TS)
├── portal/                # Developer Portal - API Consumer (React/Vite/TS)
├── mcp-gateway/           # MCP Gateway - edge-mcp mode (Python/FastAPI)
├── stoa-gateway/          # Future Rust gateway (Tokio)
├── landing-api/           # Landing page backend (Python 3.12, Poetry)
├── e2e/                   # Playwright BDD E2E tests
├── apis/                  # OpenAPI specs (per component)
├── charts/                # Helm charts
├── terraform/             # AWS IaC (EKS, RDS, etc.)
├── ansible/               # AWX playbooks
├── argocd/                # GitOps manifests
├── webmethods/            # webMethods gateway configs
├── docker/                # Docker / observability configs
└── deploy/                # Docker Compose, env configs
```

No workspace tool — each component has independent dependencies and CI.

## CI/CD (GitHub Actions)

- **Path-based triggers**: each component has its own workflow, triggered only on relevant file changes
- **Python CI**: ruff lint, mypy, pytest, bandit/safety audit
- **Node CI**: npm install, lint, format check, vitest, coverage
- **Security pipeline** (CAB-979): SAST, dependency audit, gitleaks, SBOM, container scan, DCO check
- **Dependabot**: weekly (Monday), max 5 PRs/ecosystem, prefix `chore(deps)`

## Database Migrations

- Tool: **Alembic** (in `control-plane-api/alembic/`)
- Create migration: `alembic revision --autogenerate -m "description"`
- Apply: `alembic upgrade head`

## Security Checklist

- **Gitleaks**: configured at `.gitleaks.toml` with allowlist for docs/examples
- **Bandit**: Python SAST — run `bandit -r src/`
- **Safety / pip-audit**: dependency vulnerability scanning
- **Signed commits**: verified in CI (warning-only)
- **Never commit**: `.env*`, `*.pem`, `*.key`, `*credentials*`, `*.tfvars`

## Workflow AI-Native

### Nouvelle Feature

1. **Nouvelle session** Claude Code (contexte frais)
2. **Explorer** : "Propose 3 options pour `<feature>`, ne code pas"
3. **Choisir** une option → "Plan en 5 étapes max, ne code pas"
4. **Valider** le plan → "Go"
5. **Vérifier** : tests green → commit

### Review (Décisions Importantes)

| Session | Rôle | Objectif |
|---------|------|----------|
| Session 1 | Architecte | Produire le plan d'implémentation |
| Session 2 (fresh) | Staff Engineer | Review critique du plan |
| Session 3 (fresh, optionnel) | Security Engineer | Review sécurité |

**Verdict binaire** : `Go` / `Fix` / `Refaire` — pas de "peut-être".

### Règles

- **1 chose à la fois** — ne jamais mélanger feature + refactor + fix
- **Ne jamais coder sans plan validé**
- **Red flags** (tests cassés, dette technique, faille sécu) → fix avant de continuer
- **Si > 10 min à structurer manuellement** → STOP, lance Claude Code
