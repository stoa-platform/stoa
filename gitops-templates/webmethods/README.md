# webMethods GitOps - Reconciliation Structure

> **Git Source of Truth for webMethods Gateway**
>
> This directory contains declarative definitions for APIs, policies, and aliases
> that are automatically reconciled to webMethods Gateway via AWX.

---

## Structure

```
webmethods/
├── README.md                    # This file
├── schema/
│   └── api-schema.json          # JSON Schema for CI validation
├── apis/
│   └── example-api.yaml         # API definition template
├── policies/
│   ├── jwt-validation.yaml      # JWT validation policy
│   └── rate-limit-standard.yaml # Standard rate limiting policy
├── aliases/
│   ├── dev.yaml                 # Backend endpoints for DEV
│   ├── staging.yaml             # Backend endpoints for STAGING
│   └── prod.yaml                # Backend endpoints for PROD
└── scripts/
    └── validate-webmethods.py   # Validation script for CI
```

---

## API Format (apis/*.yaml)

Each YAML file in `apis/` defines a complete API:

```yaml
apiVersion: stoa.io/v1
kind: WebMethodsAPI
metadata:
  name: my-api
  version: "1.0.0"
  description: "My API description"
  tags:
    - tag1
    - tag2
spec:
  type: REST
  basePath: /api/my-api/v1

  # Backend routing (resolved via aliases/)
  backend:
    alias: my-backend    # Reference to aliases/{env}.yaml

  # Policies applied (execution order)
  policies:
    - jwt-validation
    - rate-limit-standard

  # Authentication configuration
  auth:
    type: oauth2
    scopes:
      - my-api:read
      - my-api:write

  # Authorized applications (empty = all)
  applications: []

  # Exposed resources/endpoints
  resources:
    - path: /items
      methods: [GET, POST]
    - path: /items/{id}
      methods: [GET, PUT, DELETE]
```

---

## Policy Format (policies/*.yaml)

```yaml
apiVersion: stoa.io/v1
kind: WebMethodsPolicy
metadata:
  name: rate-limit-standard
  description: "Standard rate limiting - 100 req/min"
spec:
  type: rate-limit
  config:
    limit: 100
    interval: 60s
    key: client_id
    action: reject    # reject | queue
```

---

## Alias Format (aliases/{env}.yaml)

Aliases define backend endpoints per environment:

```yaml
apiVersion: stoa.io/v1
kind: WebMethodsAliases
metadata:
  environment: dev
aliases:
  my-backend:
    url: http://my-service.dev.svc:8080
    timeout: 30s
    retries: 3

  another-backend:
    url: http://another-service.dev.svc:8080
    timeout: 60s
    retries: 2
```

---

## Reconciliation Process

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Git Push  │────>│   ArgoCD    │────>│  AWX Job        │
│  (PR merge) │     │  PostSync   │     │  reconcile.yml  │
└─────────────┘     └─────────────┘     └────────┬────────┘
                                                 │
                                                 v
                                       ┌─────────────────┐
                                       │   webMethods    │
                                       │    Gateway      │
                                       └─────────────────┘
```

### AWX Steps:
1. **Fetch**: Clone/pull Git repository
2. **Parse**: Read YAML files (apis/, policies/, aliases/)
3. **Diff**: Compare with current Gateway state (REST API)
4. **Apply**: Create/Update/Delete to align
5. **Report**: Log results in AWX + notifications

---

## CI Validation

Before merge, the GitLab pipeline validates:

```yaml
validate-webmethods:
  stage: validate
  script:
    - pip install jsonschema pyyaml
    - python scripts/validate-webmethods.py --dir webmethods
  rules:
    - changes:
        - webmethods/**/*
```

The script validates:
- Correct YAML syntax
- Conformance to JSON Schema
- Existing alias references
- Existing policy references

---

## Usage

### Add a New API

1. Create `apis/my-new-api.yaml` following the format
2. Add required policies in `policies/`
3. Add backend aliases in `aliases/{env}.yaml`
4. Commit + PR
5. After merge -> automatic reconciliation

### Modify an Existing API

1. Edit the corresponding YAML file
2. Commit + PR
3. After merge -> automatic reconciliation

### Delete an API

1. Delete the YAML file
2. Commit + PR
3. After merge -> API removed from Gateway

---

## Template Variables

Replace these placeholders with your values:

| Variable | Description | Example |
|----------|-------------|---------|
| `${BASE_DOMAIN}` | Your base domain | `example.com` |
| `${K8S_NAMESPACE}` | Kubernetes namespace | `stoa-dev` |
| `${OIDC_ISSUER_URL}` | OIDC provider URL | `https://auth.example.com/realms/stoa` |
| `${OAUTH_AUDIENCE_API}` | API audience | `stoa-api` |
| `${OAUTH_AUDIENCE_PORTAL}` | Portal audience | `stoa-portal` |
| `${API_NAME}` | API identifier | `crm-api` |
| `${BACKEND_ALIAS}` | Backend alias name | `crm-backend` |
| `${RATE_LIMIT_REQUESTS}` | Rate limit count | `100` |
| `${RATE_LIMIT_INTERVAL}` | Rate limit window | `60s` |

---

## References

- [STOA Platform Documentation](https://github.com/stoa-platform/stoa)
- [webMethods API Gateway Documentation](https://docs.webmethods.io/)
