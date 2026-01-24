# Ansible Playbook - webMethods Gateway Reconciliation

> **Unified Tenant-Based Architecture**
>
> All APIs (admin + business) come from a single source: `stoa-catalog/tenants/`

---

## Architecture

```
tenants/
├── stoa-platform/              ← Platform/Admin APIs (internal) - 1 API
│   ├── tenant.yaml             ← portalVisibility: internal
│   └── apis/
│       └── control-plane-api/
│           └── api.yaml
│
├── acme-corp/                  ← Business APIs (public) - 3 APIs
│   ├── tenant.yaml             ← portalVisibility: public
│   └── apis/
│       ├── billing-api/
│       ├── crm-api/
│       └── inventory-api/
│
├── demo/                       ← Demo APIs (public) - 13 APIs
│   ├── tenant.yaml
│   └── apis/
│       ├── account-management-api/
│       ├── customer-360-api/
│       ├── fraud-detection-api/
│       ├── payment-api/
│       ├── petstore/
│       └── ... (+ 8 more)
│
├── high-five/                  ← Ready Player One themed (public) - 4 APIs
│   ├── tenant.yaml
│   └── apis/
│       ├── copper-key-api/
│       ├── halliday-journal-api/
│       ├── jade-key-api/
│       └── quest-api/
│
├── ioi/                        ← IOI Corporation (public) - 3 APIs
│   ├── tenant.yaml
│   └── apis/
│       ├── loyalty-api/
│       ├── sixers-army-api/
│       └── surveillance-api/
│
└── oasis/                      ← OASIS Platform (public) - 1 API
    ├── tenant.yaml
    └── apis/
        └── crystal-key-api/
```

**Total: 6 tenants, 25 APIs**

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
apiVersion: gostoa.dev/v1
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
  "https://gateway.gostoa.dev/rest/apigateway/apis" | \
  jq '.apiResponse[] | {name: .api.apiName, tags: .api.tags}'

# Check portal visibility
curl "https://portal.gostoa.dev/portal/rest/v1/apis" | \
  jq '.[].name'
# stoa-platform APIs should NOT appear
```

---

## Current Tenants

| Tenant | Visibility | APIs | Description |
|--------|------------|------|-------------|
| `stoa-platform` | `internal` | 1 | Platform admin APIs (Control-Plane-API) |
| `acme-corp` | `public` | 3 | Business APIs (CRM, Billing, Inventory) |
| `demo` | `public` | 13 | Demo/test APIs |
| `high-five` | `public` | 4 | Ready Player One - The Resistance |
| `ioi` | `public` | 3 | IOI Corporation APIs |
| `oasis` | `public` | 1 | OASIS Platform APIs |

---

## RBAC Configuration

Each tenant can define access control via `visibility` in `tenant.yaml`:

```yaml
spec:
  visibility:
    allowedRoles:
      - cpi-admin        # Platform administrators
      - tenant-admin     # Tenant administrators
      - devops           # DevOps users
      - viewer           # Read-only users
    denyRoles:
      - external-partner # Explicitly denied
```

These roles map to Keycloak realm roles defined in `control-plane-api/src/auth/rbac.py`.

---

## Links

- [stoa-catalog Repository](https://gitlab.com/cab6961310/stoa-catalog)
- [GitHub Repository](https://github.com/PotoMitan/stoa)
- [webMethods Gateway API Reference](https://documentation.softwareag.com/webmethods/api_gateway/)
