# STOA Platform Configuration Reference

This document describes all configuration options for STOA Platform components.

## Environment Configuration

The platform uses `BASE_DOMAIN` as the single source of truth for all URLs. Environment-specific configurations are in `deploy/config/{dev,staging,prod}.env`.

## Control-Plane API

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BASE_DOMAIN` | Base domain for all services | `gostoa.dev` |
| `KEYCLOAK_URL` | Keycloak server URL | `https://auth.{domain}` |
| `KEYCLOAK_REALM` | Keycloak realm name | `stoa` |
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses | `redpanda:9092` |
| `AWX_URL` | AWX automation URL | `https://awx.{domain}` |
| `CORS_ORIGINS` | Allowed CORS origins | `https://console.{domain}` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Logging Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Global log level | `INFO` |
| `LOG_FORMAT` | Output format (json/text) | `json` |
| `LOG_DEBUG_AUTH_PAYLOAD` | Debug JWT payload | `false` |
| `LOG_DEBUG_HTTP_REQUESTS` | Debug HTTP requests | `false` |
| `LOG_TRACE_ENABLED` | Enable distributed tracing | `false` |

## MCP Gateway

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPA_ENABLED` | Enable OPA policy engine | `true` |
| `OPA_EMBEDDED` | Use embedded OPA evaluator | `true` |
| `METERING_ENABLED` | Enable Kafka metering | `true` |
| `K8S_WATCHER_ENABLED` | Enable CRD watcher | `false` |

### Tool Registration (CRD)

```yaml
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
  inputSchema:
    type: object
    properties:
      query:
        type: string
```

## Console UI

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REACT_APP_API_URL` | Control-Plane API URL | Required |
| `REACT_APP_KEYCLOAK_URL` | Keycloak URL | Required |
| `REACT_APP_KEYCLOAK_REALM` | Keycloak realm | `stoa` |
| `REACT_APP_KEYCLOAK_CLIENT_ID` | OIDC client ID | `control-plane-ui` |

## Developer Portal

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_URL` | Control-Plane API URL | Required |
| `VITE_KEYCLOAK_URL` | Keycloak URL | Required |
| `VITE_KEYCLOAK_REALM` | Keycloak realm | `stoa` |
| `VITE_KEYCLOAK_CLIENT_ID` | OIDC client ID | `developer-portal` |
| `VITE_MCP_GATEWAY_URL` | MCP Gateway URL | Required |

## Helm Values

### Global Configuration

```yaml
global:
  baseDomain: gostoa.dev
  imageRegistry: ghcr.io/potomitan
  imagePullSecrets: []
```

### Control-Plane API

```yaml
controlPlaneApi:
  replicas: 2
  image:
    repository: ghcr.io/potomitan/stoa-control-plane-api
    tag: latest
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi
    requests:
      cpu: 100m
      memory: 256Mi
  database:
    host: control-plane-db
    port: 5432
    name: stoa
    secretName: db-credentials
```

### MCP Gateway

```yaml
mcpGateway:
  replicas: 2
  image:
    repository: ghcr.io/potomitan/stoa-mcp-gateway
    tag: latest
  opa:
    enabled: true
    embedded: true
  metering:
    enabled: true
    kafka:
      bootstrapServers: redpanda:9092
      topic: mcp-events
```

### Observability

```yaml
observability:
  prometheus:
    enabled: true
    serviceMonitor: true
  grafana:
    enabled: true
    dashboards: true
  loki:
    enabled: true
```

## RBAC Configuration

### Keycloak Roles

| Role | Scopes | Description |
|------|--------|-------------|
| cpi-admin | stoa:admin | Full platform access |
| tenant-admin | stoa:write, stoa:read | Manage own tenant |
| devops | stoa:write, stoa:read | Deploy and promote APIs |
| viewer | stoa:read | Read-only access |

### Realm Role Mapping

Configure in Keycloak under Realm > Roles:

1. Create roles: `cpi-admin`, `tenant-admin`, `devops`, `viewer`
2. Assign scope mappings to each role
3. Configure client scope `stoa-api` with role audience mappers

## Security Configuration

### TLS/SSL

All external endpoints require TLS. Configure certificates via:

```yaml
ingress:
  tls:
    enabled: true
    secretName: stoa-tls-secret
    # Or use cert-manager
    certManager:
      enabled: true
      issuer: letsencrypt-prod
```

### Network Policies

Enable network policies for namespace isolation:

```yaml
networkPolicies:
  enabled: true
  allowIngressFromNamespaces:
    - ingress-nginx
    - monitoring
```

## See Also

- [Installation Guide](./installation.md)
- [Architecture Overview](./ARCHITECTURE-COMPLETE.md)
- [Observability](./OBSERVABILITY.md)
