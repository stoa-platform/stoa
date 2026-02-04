---
sidebar_position: 3
title: Installation
description: Deploy STOA with Docker Compose, Helm, or from source.
---

# Installation

STOA supports three deployment methods: Docker Compose for local development, Helm for Kubernetes, and building from source.

## Docker Compose (Development)

The fastest way to run the full platform locally.

```bash
git clone https://github.com/stoa-platform/stoa.git
cd stoa
docker compose -f deploy/docker-compose.yml up -d
```

This starts all components including Keycloak, PostgreSQL, and Redpanda.

### Verify

```bash
curl http://localhost:8000/health/ready
# {"status": "ok"}
```

## Helm (Kubernetes)

Production deployment on Kubernetes 1.25+ (1.28+ recommended).

### Infrastructure Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| Nodes | 3 | 5+ |
| CPU per node | 4 cores | 8+ cores |
| Memory per node | 8 GB | 16+ GB |
| Storage | 100 GB | 500 GB SSD |

### External Dependencies

| Dependency | Purpose |
|-----------|---------|
| Keycloak | OIDC authentication |
| PostgreSQL | Application database |
| Kafka / Redpanda | Event streaming |
| GitLab | GitOps source of truth |
| Vault (optional) | Secrets management |

### Deploy

**1. Provision infrastructure** (AWS EKS example):

```bash
cd terraform/environments/dev
terraform init && terraform plan && terraform apply
```

**2. Apply CRDs**:

```bash
kubectl apply -f charts/stoa-platform/crds/
```

**3. Create namespace**:

```bash
kubectl create namespace stoa-system
```

**4. Configure values**:

Create a `values.yaml` file with your environment settings:

```yaml
global:
  domain: gostoa.dev

controlPlaneApi:
  replicas: 2
  database:
    host: your-rds-endpoint.amazonaws.com
    name: stoa
  keycloak:
    url: https://auth.gostoa.dev
    realm: stoa

mcpGateway:
  replicas: 2
  opa:
    enabled: true
    embedded: true
  metering:
    enabled: true
    kafkaBootstrap: redpanda.stoa-system:9092

portal:
  replicas: 2

consoleUi:
  replicas: 2
```

**5. Install with Helm**:

```bash
helm upgrade --install stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  -f values.yaml
```

**6. Verify**:

```bash
kubectl get pods -n stoa-system
kubectl get ingress -n stoa-system
```

### Post-Installation

1. **DNS**: Point `*.gostoa.dev` (or your domain) to the ALB/Ingress IP
2. **Keycloak**: Import the STOA realm configuration or create clients manually
3. **Demo data** (optional): `make seed-demo` to populate sample APIs and applications

## From Source

Build individual components for development.

### Control Plane API

```bash
cd control-plane-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

### Console UI

```bash
cd control-plane-ui
npm install
npm start  # http://localhost:3000
```

### Developer Portal

```bash
cd portal
npm install
npm run dev  # http://localhost:5173
```

### MCP Gateway

```bash
cd mcp-gateway
pip install -e ".[dev,k8s]"
python -m src.main  # http://localhost:8001
```

## Upgrade

```bash
helm upgrade stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  -f values.yaml
```

## Uninstall

```bash
helm uninstall stoa-platform -n stoa-system
kubectl delete namespace stoa-system
```

:::warning
Uninstalling will remove all platform resources. Ensure you have backups of your database and GitLab repositories before proceeding.
:::
