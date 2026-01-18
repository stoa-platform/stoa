# Ansible Playbook - webMethods Gateway Reconciliation

> **Unified Tenant-Based Architecture**
>
> All APIs (admin + business) come from a single source: `stoa-catalog/tenants/`

---

## Architecture

```
stoa-catalog/
└── tenants/
    ├── stoa-platform/              ← Platform/Admin APIs (internal)
    │   ├── tenant.yaml             ← portalVisibility: internal
    │   └── apis/
    │       └── control-plane-api/
    │           └── api.yaml
    │
    ├── acme-corp/                  ← Business APIs (public)
    │   ├── tenant.yaml             ← portalVisibility: public
    │   └── apis/
    │       └── crm-api/
    │           └── api.yaml
    │
    └── demo-tenant/                ← Demo APIs (public)
        ├── tenant.yaml
        └── apis/
            └── sample-api/
                └── api.yaml
```

## Features

- **Single Source**: All APIs from `stoa-catalog/tenants/`
- **Portal Visibility**: Controlled via `tenant.yaml` (`public`, `internal`, `hidden`)
- **Automatic Publish/Unpublish**: APIs published to portal based on visibility
- **Idempotent**: Multiple runs produce the same result
- **Error Isolation**: One tenant failure doesn't block others
- **Dry-run Mode**: Simulate without applying changes

---

## Usage

### Local Execution

```bash
# Install dependencies
pip install ansible pyyaml

# Reconcile DEV
ansible-playbook reconcile-webmethods.yml -e "env=dev"

# Reconcile PROD (dry-run first)
ansible-playbook reconcile-webmethods.yml -e "env=prod" --check
ansible-playbook reconcile-webmethods.yml -e "env=prod"

# With custom catalog directory
ansible-playbook reconcile-webmethods.yml \
  -e "catalog_dir=/path/to/stoa-catalog" \
  -e "env=dev"

# Without deleting orphans
ansible-playbook reconcile-webmethods.yml -e "env=dev delete_orphans=false"
```

### Via AWX

1. Import configuration from `awx/awx-config.yml`
2. Launch job using the survey form
3. Or trigger via webhook from ArgoCD/GitLab

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CATALOG_DIR` | Path to stoa-catalog | `playbook_dir/../..` |
| `STOA_ENV` | Target environment | `dev` |
| `WM_GATEWAY_URL` | webMethods Gateway URL | `http://apim-gateway:5555` |
| `WM_ADMIN_USER` | Gateway admin user | `Administrator` |
| `WM_ADMIN_PASSWORD` | Admin password | (required) |
| `PORTAL_GATEWAY_ID` | Portal Gateway ID | `default` |
| `DELETE_ORPHANS` | Delete orphaned APIs | `true` |

---

## Portal Visibility Matrix

| `portalVisibility` | Developer Portal | Gateway | MCP Tools | Use Case |
|--------------------|------------------|---------|-----------|----------|
| `public` | Visible | Accessible | Exposed | Business APIs |
| `internal` | Hidden | Accessible | Admins only | Platform APIs |
| `hidden` | Hidden | Accessible | Not exposed | Technical APIs |

---

## Reconciliation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: LOAD                                                  │
│  ├── Find all tenants in catalog_dir/tenants/                   │
│  ├── Load tenant.yaml (extract portalVisibility)                │
│  └── Load all apis/{api}/api.yaml per tenant                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: FETCH                                                 │
│  └── GET /rest/apigateway/apis (current state)                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3: DIFF                                                  │
│  ├── APIs to create (Git - Gateway)                             │
│  ├── APIs to delete (Gateway - Git)                             │
│  └── APIs to update (Git ∩ Gateway)                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 4: SYNC                                                  │
│  ├── POST /apis (create new)                                    │
│  ├── PUT /apis/{id} (update existing)                           │
│  └── DELETE /apis/{id} (remove orphans)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 5: PORTAL                                                │
│  ├── PUT /apis/{id}/publish (portalVisibility: public)          │
│  └── PUT /apis/{id}/unpublish (portalVisibility: internal)      │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
ansible/reconcile-webmethods/
├── reconcile-webmethods.yml    # Main playbook
├── README.md                   # This file
└── tasks/
    ├── load-tenant.yml         # Load tenant config + list APIs
    ├── load-api.yml            # Load single API with metadata
    ├── sync-api-unified.yml    # Create/update API in Gateway
    ├── delete-api.yml          # Delete orphaned API
    ├── publish-to-portal.yml   # Publish public API
    ├── unpublish-from-portal.yml # Unpublish internal API
    └── notify.yml              # Send notifications
```

---

## tenant.yaml Schema

```yaml
apiVersion: stoa.io/v1
kind: Tenant
metadata:
  name: my-tenant
  displayName: "My Tenant"

spec:
  # Portal visibility: public | internal | hidden
  portalVisibility: public

  visibility:
    allowedRoles:
      - developer
      - api-consumer
    denyRoles: []

  defaultPolicies:
    - name: rate-limit-standard
      config:
        requestsPerMinute: 100

  tags:
    - business
    - external

  contact:
    team: "My Team"
    email: "api@example.com"
```

---

## api.yaml Schema

```yaml
apiVersion: stoa.cab-i.com/v1
kind: API
metadata:
  name: my-api
  version: "1.0"

spec:
  displayName: "My API"
  description: "API description"
  status: published
  category: integration

  tags:
    - rest
    - external

  backend:
    url: https://backend.example.com/api

  # Override tenant visibility (optional)
  portalVisibility: public

  gateway:
    type: REST
    isActive: true
```

---

## ArgoCD Integration

The `stoa-webmethods-gitops` application watches `stoa-catalog/tenants/` and triggers reconciliation via PostSync hook.

```yaml
# argocd/apps/stoa-webmethods-gitops.yaml
source:
  repoURL: https://gitlab.com/cab6961310/stoa-catalog.git
  targetRevision: main
  path: tenants
```

---

## Migration from Multi-Source

If migrating from the old multi-source architecture:

```bash
# Run migration script
./scripts/migrate-admin-apis.sh \
  --gitops-dir=/path/to/stoa-gitops \
  --catalog-dir=/path/to/stoa-catalog \
  --dry-run

# Review and apply
./scripts/migrate-admin-apis.sh \
  --gitops-dir=/path/to/stoa-gitops \
  --catalog-dir=/path/to/stoa-catalog
```

---

## Verification

```bash
# Check APIs in Gateway
curl -u Administrator:password \
  "https://gateway.stoa.cab-i.com/rest/apigateway/apis" | \
  jq '.apiResponse[] | {name: .api.apiName, tags: .api.tags}'

# Check portal visibility
curl "https://portal.stoa.cab-i.com/portal/rest/v1/apis" | \
  jq '.[].name'
# stoa-platform APIs should NOT appear
```

---

## Links

- [stoa-catalog Repository](https://gitlab.com/cab6961310/stoa-catalog)
- [webMethods Gateway API Reference](https://documentation.softwareag.com/webmethods/api_gateway/)
