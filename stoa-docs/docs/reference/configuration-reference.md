---
sidebar_position: 3
title: Configuration Reference
description: Complete reference for all configuration options.
---

# Configuration Reference

This page documents every configurable option across all STOA components.

## Control Plane API

### Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HOST` | string | `0.0.0.0` | Bind address |
| `PORT` | integer | `8000` | Bind port |
| `WORKERS` | integer | `4` | Uvicorn worker count |
| `BASE_DOMAIN` | string | `gostoa.dev` | Base domain for URL derivation |
| `CORS_ORIGINS` | string | `*` | Comma-separated allowed origins |

### Database

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DATABASE_URL` | string | — | PostgreSQL connection string |
| `DB_POOL_SIZE` | integer | `10` | Connection pool size |
| `DB_MAX_OVERFLOW` | integer | `20` | Max additional connections |
| `DB_POOL_TIMEOUT` | integer | `30` | Pool checkout timeout (seconds) |
| `DB_ECHO` | boolean | `false` | Log SQL statements |

Format: `postgresql+asyncpg://user:pass@host:5432/stoa`

### Keycloak

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `KEYCLOAK_URL` | string | `https://auth.{BASE_DOMAIN}` | Keycloak base URL |
| `KEYCLOAK_REALM` | string | `stoa` | Realm name |
| `KEYCLOAK_CLIENT_ID` | string | `control-plane-api` | Backend client ID |
| `KEYCLOAK_CLIENT_SECRET` | string | — | Backend client secret |
| `KEYCLOAK_JWKS_CACHE_TTL` | integer | `3600` | JWKS cache TTL (seconds) |

### Kafka

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | string | `localhost:9092` | Broker addresses |
| `KAFKA_SECURITY_PROTOCOL` | string | `PLAINTEXT` | Protocol: `PLAINTEXT`, `SSL`, `SASL_SSL` |
| `KAFKA_SASL_MECHANISM` | string | — | SASL mechanism if using SASL |
| `KAFKA_SASL_USERNAME` | string | — | SASL username |
| `KAFKA_SASL_PASSWORD` | string | — | SASL password |

### AWX

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AWX_URL` | string | `https://awx.{BASE_DOMAIN}` | AWX server URL |
| `AWX_TOKEN` | string | — | AWX API token |
| `AWX_VERIFY_SSL` | boolean | `true` | Verify TLS certificates |

### GitLab

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GITLAB_URL` | string | — | GitLab instance URL |
| `GITLAB_TOKEN` | string | — | Personal access token |
| `GITLAB_GROUP_ID` | integer | — | Parent group for tenant repos |

### Vault

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VAULT_URL` | string | — | Vault server URL |
| `VAULT_TOKEN` | string | — | Vault authentication token |
| `VAULT_MOUNT` | string | `secret` | KV secrets engine mount |
| `VAULT_VERIFY_SSL` | boolean | `true` | Verify TLS certificates |

### Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOG_LEVEL` | string | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | string | `json` | `json` or `text` |
| `LOG_ACCESS` | boolean | `true` | Log HTTP access requests |

## MCP Gateway

### Core

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HOST` | string | `0.0.0.0` | Bind address |
| `PORT` | integer | `8001` | Bind port |
| `GATEWAY_MODE` | string | `edge-mcp` | Gateway mode |

### OPA

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPA_ENABLED` | boolean | `true` | Enable policy engine |
| `OPA_EMBEDDED` | boolean | `true` | Use embedded evaluator |
| `OPA_POLICY_PATH` | string | `policies/` | Path to Rego policy files |
| `OPA_EXTERNAL_URL` | string | — | External OPA server URL (if not embedded) |
| `OPA_DECISION_PATH` | string | `stoa/mcp/allow` | OPA decision path |

### Metering

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `METERING_ENABLED` | boolean | `true` | Enable metering pipeline |
| `METERING_TOPIC` | string | `stoa.metering` | Kafka topic for metering events |
| `METERING_BATCH_SIZE` | integer | `100` | Batch size before flush |
| `METERING_FLUSH_INTERVAL` | integer | `5` | Flush interval (seconds) |

### Kubernetes

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `K8S_WATCHER_ENABLED` | boolean | `false` | Enable CRD watcher |
| `K8S_NAMESPACE` | string | — | Namespace to watch (empty = all) |
| `K8S_KUBECONFIG` | string | — | Kubeconfig path (empty = in-cluster) |

## Console UI

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `REACT_APP_API_URL` | string | `https://api.{BASE_DOMAIN}` | API endpoint |
| `REACT_APP_KEYCLOAK_URL` | string | `https://auth.{BASE_DOMAIN}` | Keycloak URL |
| `REACT_APP_KEYCLOAK_REALM` | string | `stoa` | Keycloak realm |
| `REACT_APP_KEYCLOAK_CLIENT_ID` | string | `control-plane-ui` | OIDC client ID |
| `REACT_APP_TITLE` | string | `STOA Console` | Browser tab title |

## Developer Portal

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VITE_API_URL` | string | `https://api.{BASE_DOMAIN}` | API endpoint |
| `VITE_KEYCLOAK_URL` | string | `https://auth.{BASE_DOMAIN}` | Keycloak URL |
| `VITE_KEYCLOAK_REALM` | string | `stoa` | Keycloak realm |
| `VITE_KEYCLOAK_CLIENT_ID` | string | `stoa-portal` | OIDC client ID |
| `VITE_MCP_GATEWAY_URL` | string | `https://mcp.{BASE_DOMAIN}` | MCP Gateway URL |
| `VITE_APP_TITLE` | string | `STOA Portal` | Browser tab title |

## Helm Chart Values

### Global

```yaml
global:
  domain: gostoa.dev              # BASE_DOMAIN
  imagePullPolicy: IfNotPresent
  imageRegistry: ""               # Custom registry prefix
```

### Per-Component

```yaml
controlPlaneApi:
  replicas: 2
  image:
    repository: stoa-platform/control-plane-api
    tag: latest
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 1000m
      memory: 1Gi
  database:
    host: ""
    port: 5432
    name: stoa
    secretName: stoa-db-credentials
  keycloak:
    url: ""            # Override auto-derived URL
    realm: stoa

mcpGateway:
  replicas: 2
  image:
    repository: stoa-platform/mcp-gateway
    tag: latest
  resources:
    requests:
      cpu: 250m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi
  opa:
    enabled: true
    embedded: true
  metering:
    enabled: true
    kafkaBootstrap: redpanda.stoa-system:9092

portal:
  replicas: 2
  image:
    repository: stoa-platform/portal
    tag: latest

consoleUi:
  replicas: 2
  image:
    repository: stoa-platform/console-ui
    tag: latest
```

### Observability

```yaml
observability:
  prometheus:
    enabled: true
    retention: 15d
  grafana:
    enabled: true
    adminPassword: ""   # Set via secret
  loki:
    enabled: true
    retention: 7d
```

### Ingress

```yaml
ingress:
  enabled: true
  className: alb
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
  tls:
    enabled: true
    secretName: stoa-tls
```
