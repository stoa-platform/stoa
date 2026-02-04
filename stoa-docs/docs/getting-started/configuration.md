---
sidebar_position: 4
title: Configuration
description: Environment variables and YAML configuration reference.
---

# Configuration

STOA uses `BASE_DOMAIN` as the single source of truth for deriving all service URLs. Each component reads its configuration from environment variables.

## Base Domain

Set `BASE_DOMAIN` and all service URLs are derived automatically:

```bash
BASE_DOMAIN=gostoa.dev
# → Console:  https://console.gostoa.dev
# → Portal:   https://portal.gostoa.dev
# → API:      https://api.gostoa.dev
# → MCP:      https://mcp.gostoa.dev
# → Auth:     https://auth.gostoa.dev
```

## Control Plane API

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DOMAIN` | `gostoa.dev` | Base domain for all services |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `KEYCLOAK_URL` | `https://auth.{BASE_DOMAIN}` | Keycloak server URL |
| `KEYCLOAK_REALM` | `stoa` | Keycloak realm name |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka/Redpanda broker list |
| `AWX_URL` | `https://awx.{BASE_DOMAIN}` | AWX automation server URL |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FORMAT` | `json` | Log format (`json` or `text`) |

## MCP Gateway

| Variable | Default | Description |
|----------|---------|-------------|
| `OPA_ENABLED` | `true` | Enable OPA policy engine |
| `OPA_EMBEDDED` | `true` | Use embedded OPA evaluator (vs external) |
| `METERING_ENABLED` | `true` | Enable Kafka-based metering pipeline |
| `K8S_WATCHER_ENABLED` | `false` | Enable CRD watcher for dynamic tool registration |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka/Redpanda broker list |

## Console UI

| Variable | Default | Description |
|----------|---------|-------------|
| `REACT_APP_API_URL` | `https://api.{BASE_DOMAIN}` | Control Plane API endpoint |
| `REACT_APP_KEYCLOAK_URL` | `https://auth.{BASE_DOMAIN}` | Keycloak URL |
| `REACT_APP_KEYCLOAK_REALM` | `stoa` | Keycloak realm |
| `REACT_APP_KEYCLOAK_CLIENT_ID` | `control-plane-ui` | OIDC client ID |

## Developer Portal

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `https://api.{BASE_DOMAIN}` | Control Plane API endpoint |
| `VITE_KEYCLOAK_URL` | `https://auth.{BASE_DOMAIN}` | Keycloak URL |
| `VITE_KEYCLOAK_REALM` | `stoa` | Keycloak realm |
| `VITE_KEYCLOAK_CLIENT_ID` | `stoa-portal` | OIDC client ID |
| `VITE_MCP_GATEWAY_URL` | `https://mcp.{BASE_DOMAIN}` | MCP Gateway endpoint |

## Helm Values

The Helm chart exposes these top-level configuration blocks:

```yaml
global:
  domain: gostoa.dev          # BASE_DOMAIN equivalent

controlPlaneApi:
  replicas: 2
  resources:
    requests: { cpu: 250m, memory: 512Mi }
    limits: { cpu: 1000m, memory: 1Gi }
  database:
    host: ""
    port: 5432
    name: stoa
    secretName: stoa-db-credentials

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

observability:
  prometheus:
    enabled: true
  grafana:
    enabled: true
  loki:
    enabled: true
```

## Environment Files

Per-environment configuration lives in `deploy/config/`:

```
deploy/config/
├── dev.env
├── staging.env
└── prod.env
```

Each file sets the environment variables for its target environment. The Helm chart reads from these during deployment.

## RBAC Configuration

STOA defines four roles via Keycloak client scopes:

| Role | Scope | Access Level |
|------|-------|-------------|
| `cpi-admin` | `stoa:admin` | Full platform access |
| `tenant-admin` | `stoa:write`, `stoa:read` | Manage own tenant |
| `devops` | `stoa:write`, `stoa:read` | Deploy and promote APIs |
| `viewer` | `stoa:read` | Read-only access |

See [Authentication](../guides/authentication) for Keycloak setup details.
