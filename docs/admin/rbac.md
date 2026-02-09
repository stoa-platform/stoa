# RBAC — Role-Based Access Control

## Role Overview

STOA Platform uses 4 roles, enforced through Keycloak realm roles and mapped to API scopes.

| Role | Scope | Description |
|------|-------|-------------|
| `cpi-admin` | `stoa:admin` | Full platform access — manage all tenants, users, configuration |
| `tenant-admin` | `stoa:write`, `stoa:read` | Own tenant — manage APIs, applications, subscriptions |
| `devops` | `stoa:write`, `stoa:read` | Deploy and promote — manage deployments and gateway config |
| `viewer` | `stoa:read` | Read-only — view APIs, dashboards, monitoring |

## Permissions Matrix

| Action | cpi-admin | tenant-admin | devops | viewer |
|--------|-----------|-------------|--------|--------|
| Create/delete tenants | Yes | No | No | No |
| Manage platform settings | Yes | No | No | No |
| View all tenants | Yes | No | No | No |
| Create/edit APIs (own tenant) | Yes | Yes | No | No |
| Manage applications | Yes | Yes | No | No |
| Approve subscriptions | Yes | Yes | No | No |
| Deploy gateway config | Yes | Yes | Yes | No |
| Promote API versions | Yes | Yes | Yes | No |
| View APIs and catalog | Yes | Yes | Yes | Yes |
| View monitoring dashboards | Yes | Yes | Yes | Yes |
| View audit logs | Yes | Yes | Yes | Yes |

## Keycloak Configuration

### Realm Roles

In the `stoa` realm, create these realm roles:

| Realm Role | Description |
|-----------|-------------|
| `cpi-admin` | Platform administrator |
| `tenant-admin` | Tenant administrator |
| `devops` | DevOps / deployment operator |
| `viewer` | Read-only user |

### Client Scopes

Create the following client scopes in Keycloak:

| Client Scope | Type | Mapped Roles |
|-------------|------|-------------|
| `stoa:admin` | Optional | `cpi-admin` |
| `stoa:write` | Optional | `tenant-admin`, `devops` |
| `stoa:read` | Default | All roles |

### Client Configuration

The `control-plane-ui` client needs:

```
Client ID:           control-plane-ui
Client Protocol:     openid-connect
Access Type:         public (PKCE)
Valid Redirect URIs: https://console.<BASE_DOMAIN>/*
                     https://portal.<BASE_DOMAIN>/*
Web Origins:         https://console.<BASE_DOMAIN>
                     https://portal.<BASE_DOMAIN>
Default Scopes:      stoa:read
Optional Scopes:     stoa:admin, stoa:write
```

### Token Claims

Roles are included in the JWT `realm_access.roles` claim:

```json
{
  "realm_access": {
    "roles": ["tenant-admin"]
  },
  "scope": "openid stoa:read stoa:write",
  "tenant_id": "tenant-acme"
}
```

## API Enforcement

The Control Plane API checks scopes on every request:

```
Authorization: Bearer <JWT>
```

| Endpoint Pattern | Required Scope |
|-----------------|---------------|
| `GET /v1/*` | `stoa:read` |
| `POST /v1/*`, `PUT /v1/*`, `DELETE /v1/*` | `stoa:write` |
| `POST /v1/tenants`, `DELETE /v1/tenants/*` | `stoa:admin` |
| `GET /v1/admin/*` | `stoa:admin` |

## Multi-Tenancy Isolation

Each tenant gets:

- A Kubernetes namespace: `tenant-<name>`
- Isolated API catalog entries
- Separate subscription and application data
- Tenant-scoped MCP Tool CRDs

A `tenant-admin` can only access resources within their own tenant. Cross-tenant access requires `cpi-admin`.

## Adding a User

### Via Keycloak Admin Console

1. Go to `https://auth.<BASE_DOMAIN>/admin`
2. Select the `stoa` realm
3. Navigate to **Users** > **Add user**
4. Fill in username, email, first/last name
5. Go to the **Role Mappings** tab
6. Assign the appropriate realm role (e.g., `tenant-admin`)
7. Set the user's tenant in **Attributes**: key = `tenant_id`, value = `tenant-acme`

### Via Keycloak API

```bash
# Get admin token
ADMIN_TOKEN=$(curl -s -X POST "https://auth.<BASE_DOMAIN>/realms/master/protocol/openid-connect/token" \
  -d "grant_type=client_credentials&client_id=admin-cli&client_secret=<secret>" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create user
curl -X POST "https://auth.<BASE_DOMAIN>/admin/realms/stoa/users" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "new-user",
    "email": "user@example.com",
    "enabled": true,
    "attributes": { "tenant_id": ["tenant-acme"] },
    "credentials": [{ "type": "password", "value": "changeme", "temporary": true }]
  }'
```

## Auditing

All access decisions are logged by the Control Plane API. Check audit logs:

```bash
kubectl logs -f deploy/control-plane-api -n stoa-system | grep "authz"
```

Keycloak also provides event logging for login attempts, token grants, and role changes.
