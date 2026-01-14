# Platform Bootstrap Configuration

This directory contains the core platform configurations required for STOA to function properly.

## Overview

These configurations define:
- **APIs** exposed through the API Gateway
- **Applications** (OAuth2 clients) for Portal, Console, and MCP Gateway
- **Policies** for security, rate limiting, and logging
- **Scopes** for authorization

## Directory Structure

```
platform-bootstrap/
├── README.md                    # This file
├── kustomization.yaml           # Kustomize configuration
├── apis/                        # API Gateway configurations
│   └── control-plane-api.yaml   # Core STOA API
├── applications/                # OAuth2 application configs
│   ├── control-plane-ui.yaml    # Console (API Provider)
│   ├── stoa-portal.yaml         # Portal (API Consumer)
│   └── mcp-gateway.yaml         # MCP Gateway (AI-Native)
├── policies/                    # Gateway policies
│   ├── jwt-validation.yaml      # Token validation
│   ├── rate-limit-standard.yaml # Rate limiting
│   ├── cors-platform.yaml       # CORS for frontends
│   └── logging-standard.yaml    # Audit logging
└── scopes/                      # OAuth2 scopes
    └── stoa-scopes.yaml         # Platform scopes
```

## Deployment Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  GitHub Actions │────▶│  GitLab Sync    │────▶│  AWX/ArgoCD     │
│  (Validate)     │     │  (stoa-gitops)  │     │  (Apply)        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │  API Gateway    │
                                               │  (webMethods)   │
                                               └─────────────────┘
```

## CI/CD Pipeline

The `platform-config-ci.yml` workflow:

1. **Validate** - Lint YAML, check required fields, validate cross-references
2. **Sync to GitLab** - Push configs to `stoa-gitops` repository
3. **Reconcile Gateway** - Trigger AWX job to apply changes
4. **Verify** - Check API is accessible on Gateway
5. **Notify** - Send Slack notification

### Triggers

- Push to `main` branch with changes in:
  - `deploy/platform-bootstrap/**`
  - `gitops-templates/webmethods/**`
- Manual trigger via `workflow_dispatch`

## Manual Deployment

### Initialize Platform

```bash
# Full initialization (validates, syncs, triggers reconciliation)
./scripts/init-platform-bootstrap.sh --env dev

# Dry run (validation only)
./scripts/init-platform-bootstrap.sh --env dev --dry-run
```

### Validate Only

```bash
python scripts/validate-platform-config.py --dir deploy/platform-bootstrap
```

### Sync to GitLab Manually

```bash
export GITLAB_TOKEN="your-token"
./scripts/init-platform-bootstrap.sh --env dev
```

## Configuration Reference

### API Configuration

```yaml
apiVersion: stoa.io/v1
kind: WebMethodsAPI
metadata:
  name: API-Name
  version: "1.0"
spec:
  type: REST
  basePath: /gateway/API-Name/1.0
  backend:
    url: https://backend.example.com
  auth:
    type: oauth2
    scopes: [scope:read, scope:write]
  policies:
    - jwt-validation
    - rate-limit-standard
```

### Application Configuration

```yaml
apiVersion: stoa.io/v1
kind: Application
metadata:
  name: my-app
spec:
  displayName: My Application
  oauth2:
    clientId: my-app
    grantTypes: [authorization_code, refresh_token]
    redirectUris: [https://app.example.com/*]
  subscriptions:
    - apiName: API-Name
      scopes: [scope:read]
```

### Policy Configuration

```yaml
apiVersion: stoa.io/v1
kind: Policy
metadata:
  name: my-policy
spec:
  type: rate-limit
  order: 20
  config:
    requests: 100
    window: 60
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DOMAIN` | `stoa.cab-i.com` | Base domain for URLs |
| `GITLAB_TOKEN` | - | GitLab access token |
| `GITLAB_PROJECT` | `stoa-platform/stoa-gitops` | GitLab project path |
| `AWX_URL` | `https://awx.${BASE_DOMAIN}` | AWX server URL |
| `AWX_TOKEN` | - | AWX API token |

## Adding New APIs

1. Create a new file in `apis/`:
   ```bash
   cp apis/control-plane-api.yaml apis/my-new-api.yaml
   ```

2. Edit the configuration for your API

3. Add the API to applications that need access:
   ```yaml
   subscriptions:
     - apiName: My-New-API
       scopes: [my-api:read]
   ```

4. Commit and push - CI/CD will handle deployment

## Troubleshooting

### API not accessible on Gateway

1. Check GitLab sync:
   ```bash
   git -C /tmp/stoa-gitops log -1
   ```

2. Check AWX job status:
   ```bash
   curl -H "Authorization: Bearer $AWX_TOKEN" \
     https://awx.stoa.cab-i.com/api/v2/jobs/?order_by=-id
   ```

3. Check Gateway directly:
   ```bash
   curl https://gateway.stoa.cab-i.com/rest/apigateway/apis
   ```

### Validation Errors

Run validation locally:
```bash
python scripts/validate-platform-config.py --dir deploy/platform-bootstrap --strict
```

### CORS Issues

Ensure the origin is in `policies/cors-platform.yaml`:
```yaml
allowOrigins:
  - https://your-origin.example.com
```
