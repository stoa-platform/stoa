---
sidebar_position: 4
title: Authentication
description: OIDC and Keycloak setup for STOA.
---

# Authentication

STOA uses **Keycloak** as its identity provider, implementing OpenID Connect (OIDC) for all user-facing applications and machine-to-machine communication.

## Architecture

```
┌──────────┐   OIDC    ┌──────────┐
│ Console  │◄─────────►│          │
│ UI       │           │          │
└──────────┘           │          │
                       │ Keycloak │
┌──────────┐   OIDC    │          │
│ Portal   │◄─────────►│          │
└──────────┘           │          │
                       │          │
┌──────────┐   JWT     │          │
│ API      │◄─────────►│          │
└──────────┘           └──────────┘
```

## OIDC Clients

STOA uses two Keycloak clients for the frontend applications:

| Client ID | Application | Type |
|-----------|-------------|------|
| `control-plane-ui` | Console UI | Public (SPA) |
| `stoa-portal` | Developer Portal | Public (SPA) |

Both use the **Authorization Code flow with PKCE** for browser-based authentication.

### Client Configuration

Each client requires:

- **Valid Redirect URIs**: `https://console.gostoa.dev/*` and `https://portal.gostoa.dev/*`
- **Web Origins**: Matching the redirect URIs
- **Standard Flow**: Enabled
- **Direct Access Grants**: Enabled (for CLI and service accounts)

## Realm Configuration

### STOA Realm

Create a Keycloak realm named `stoa` with the following:

1. **Clients**: `control-plane-ui` and `stoa-portal`
2. **Client Scopes**: `stoa:admin`, `stoa:write`, `stoa:read`
3. **Groups**: Map to RBAC roles
4. **Users**: Create with appropriate group membership

### Client Scopes

| Scope | Purpose | Assigned To |
|-------|---------|-------------|
| `stoa:admin` | Full platform access | `cpi-admin` group |
| `stoa:write` | Create/update operations | `tenant-admin`, `devops` groups |
| `stoa:read` | Read-only access | `viewer` group |

### Mapping Groups to Scopes

1. Create groups: `cpi-admin`, `tenant-admin`, `devops`, `viewer`
2. Assign client scopes to groups via **Scope Mappings**
3. Add users to groups

## Token Structure

STOA expects the following claims in the JWT access token:

```json
{
  "sub": "user-uuid",
  "email": "admin@gostoa.dev",
  "realm_access": {
    "roles": ["cpi-admin"]
  },
  "scope": "openid stoa:admin stoa:write stoa:read",
  "tenant": "acme"
}
```

### Token Validation

The Control Plane API validates tokens on every request:

1. Verify JWT signature against Keycloak's JWKS endpoint
2. Check `iss` (issuer) matches the Keycloak realm URL
3. Check `aud` (audience) matches the client ID
4. Check token expiration (`exp`)
5. Extract scopes for RBAC evaluation

## Frontend Auth Flow

Both the Console and Portal use `react-oidc-context` for authentication:

1. User clicks **Sign In**
2. Redirect to Keycloak login page
3. User authenticates (username/password, SSO, or social login)
4. Keycloak redirects back with authorization code
5. Frontend exchanges code for tokens (via PKCE)
6. Tokens stored in `sessionStorage`
7. Automatic token refresh before expiry

### Session Storage

OIDC tokens are stored in `sessionStorage` (not `localStorage`) for security:

- `oidc.user:{keycloak-url}/realms/stoa:{client-id}`

This means sessions are per-tab and cleared when the browser tab is closed.

## Machine-to-Machine Auth

For CI/CD, scripts, and service accounts, use the **Client Credentials Grant** or **Password Grant**:

### Password Grant (CLI)

```bash
curl -X POST https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token \
  -d "grant_type=password" \
  -d "client_id=control-plane-ui" \
  -d "username=admin@gostoa.dev" \
  -d "password=<password>"
```

### Client Credentials Grant (Service)

```bash
curl -X POST https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token \
  -d "grant_type=client_credentials" \
  -d "client_id=stoa-service" \
  -d "client_secret=<secret>"
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| 401 on all API calls | Token expired or invalid | Re-authenticate, check token expiry |
| CORS errors on login | Keycloak Web Origins misconfigured | Add application URL to Web Origins |
| Redirect loop | Redirect URI mismatch | Update Valid Redirect URIs in Keycloak |
| Token missing scopes | User not in correct group | Add user to appropriate Keycloak group |

See [Troubleshooting](../reference/troubleshooting) for more common issues.
