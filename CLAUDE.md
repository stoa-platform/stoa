# CLAUDE.md - Instructions for Claude Code

## Project Overview
STOA Platform v2 - Multi-tenant API Management with:
- UI RBAC Control-Plane (React + Keycloak)
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
- **charts/stoa-platform/**: Helm chart for K8s deployment
- **terraform/**: AWS infrastructure (EKS, RDS, etc.)

### Key Technologies
- **Frontend**: React 18, TypeScript, Keycloak-js
- **Backend**: FastAPI, Python 3.11, kafka-python
- **Infrastructure**: EKS, RDS PostgreSQL, ALB
- **Event Streaming**: Redpanda (Kafka-compatible)
- **Auth**: Keycloak (OIDC)
- **GitOps**: GitLab + Webhooks
- **Automation**: AWX (Ansible Tower)

### RBAC Roles
1. **cpi-admin**: Full platform access
2. **tenant-admin**: Manage own tenant
3. **devops**: Deploy and promote APIs
4. **viewer**: Read-only access

## Common Tasks

### Development
```bash
# UI Development
cd control-plane-ui && npm install && npm start

# API Development
cd control-plane-api && pip install -r requirements.txt && uvicorn src.main:app --reload

# Helm lint
helm lint charts/stoa-platform
```

### Deployment
```bash
# Terraform
cd terraform/environments/dev
terraform init && terraform plan && terraform apply

# Helm
helm upgrade --install stoa-platform ./charts/stoa-platform -n stoa-system --create-namespace
```

## Key URLs
- Console: https://console.dev.stoa.cab-i.com
- API: https://api.dev.stoa.cab-i.com
- Gateway: https://gateway.dev.stoa.cab-i.com
- Keycloak: https://keycloak.dev.stoa.cab-i.com
