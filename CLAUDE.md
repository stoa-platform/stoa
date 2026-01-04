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

## Architecture

### Components
- **control-plane-ui/**: React TypeScript UI with RBAC
- **control-plane-api/**: FastAPI backend with Keycloak auth
- **mcp-gateway/**: MCP Gateway for AI-Native API access
- **charts/stoa-platform/**: Helm chart for K8s deployment
- **terraform/**: AWS infrastructure (EKS, RDS, etc.)

### MCP Gateway Features (Phase 12)
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
# UI Development
cd control-plane-ui && npm install && npm start

# API Development
cd control-plane-api && pip install -r requirements.txt && uvicorn src.main:app --reload

# MCP Gateway Development
cd mcp-gateway && pip install -e ".[dev,k8s]" && python -m src.main

# Run MCP Gateway tests
cd mcp-gateway && pytest --cov=src

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
apiVersion: stoa.cab-i.com/v1alpha1
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
- DevOps UI: https://devops.stoa.cab-i.com
- API: https://api.stoa.cab-i.com
- Gateway: https://gateway.stoa.cab-i.com
- MCP Gateway: https://mcp.stoa.cab-i.com
- Keycloak: https://auth.stoa.cab-i.com
- AWX: https://awx.stoa.cab-i.com
- ArgoCD: https://argocd.stoa.cab-i.com
- Vault: https://vault.stoa.cab-i.com

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
