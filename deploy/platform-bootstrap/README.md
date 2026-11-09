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

## Continuous Integration

The `platform-config-ci.yml` workflow validates these configs. It does not sync
or deploy them anywhere.

1. **Validate** - Lint YAML, check required fields, validate cross-references,
   report variables without defaults
2. **Notify** - On `main`, send the validation result to Slack

The former sync to the `stoa-gitops` repository was removed: that repository is
abandoned and no ArgoCD application reads it.

### Triggers

- Pull requests and pushes to `main` with changes in:
  - `deploy/platform-bootstrap/**`
- Manual trigger via `workflow_dispatch`

## Local Validation

```bash
python scripts/validate-platform-config.py --dir deploy/platform-bootstrap
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
| `BASE_DOMAIN` | `gostoa.dev` | Base domain for URLs |

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

4. Open a pull request - CI validates the configs

## Troubleshooting

### API not accessible on Gateway

1. Check ArgoCD sync status:
   ```bash
   kubectl get applications -n argocd
   ```

2. Check Gateway directly:
   ```bash
   curl https://vps-wm.gostoa.dev/rest/apigateway/apis
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
