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
