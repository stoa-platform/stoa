# Keycloak Audience Mappers Configuration

## Overview

This document explains how to configure Keycloak Audience Mappers to follow OAuth2/OIDC best practices for token audience validation.

## OAuth2 Best Practices

In OAuth2/OIDC, the JWT token contains important claims:

| Claim | Meaning | Example |
|-------|---------|---------|
| `aud` (audience) | **Who should consume this token** (the API/Resource Server) | `control-plane-api` |
| `azp` (authorized party) | **Who requested this token** (the client application) | `control-plane-ui` |
| `iss` (issuer) | **Who issued this token** (the IdP) | `https://auth.stoa.cab-i.com/realms/stoa` |

### Current Issue

By default, Keycloak sets `aud` to the client ID that requested the token:

```json
{
  "aud": "control-plane-ui",  // Wrong: this is the client, not the API
  "azp": "control-plane-ui",
  "iss": "https://auth.stoa.cab-i.com/realms/stoa"
}
```

### Correct Configuration

After configuring Audience Mappers:

```json
{
  "aud": "control-plane-api",  // Correct: the API that will validate this token
  "azp": "control-plane-ui",   // The client that requested the token
  "iss": "https://auth.stoa.cab-i.com/realms/stoa"
}
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Keycloak                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Clients (Applications requesting tokens):                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ control-plane-ui │  │ stoa-portal      │  │ mcp-gateway-     │   │
│  │ (public/PKCE)    │  │ (public/PKCE)    │  │ client           │   │
│  │                  │  │                  │  │ (confidential)   │   │
│  │ + Audience       │  │ + Audience       │  │ + Audience       │   │
│  │   Mapper ────────┼──┼──────────────────┼──┼───────┐          │   │
│  └──────────────────┘  └──────────────────┘  └───────┼──────────┘   │
│                                                       │              │
│                                                       ▼              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Resource Server (API)                            │   │
│  │                   control-plane-api                           │   │
│  │                                                               │   │
│  │  This is NOT a client that authenticates.                    │   │
│  │  It's the identifier of the API that VALIDATES tokens.       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Configuration Scripts

### Prerequisites

- `jq` installed
- `curl` installed
- Keycloak admin credentials

### Option 1: Bash Script

```bash
export KEYCLOAK_URL="https://auth.stoa.cab-i.com"
export KEYCLOAK_REALM="stoa"
export KEYCLOAK_ADMIN_USER="admin"
export KEYCLOAK_ADMIN_PASS="your-admin-password"
export RESOURCE_SERVER_ID="control-plane-api"

# Dry run first
DRY_RUN=true ./configure-keycloak-audience.sh

# Apply changes
DRY_RUN=false ./configure-keycloak-audience.sh
```

### Option 2: Python Script

```bash
export KEYCLOAK_URL="https://auth.stoa.cab-i.com"
export KEYCLOAK_REALM="stoa"
export KEYCLOAK_ADMIN_USER="admin"
export KEYCLOAK_ADMIN_PASS="your-admin-password"
export RESOURCE_SERVER_ID="control-plane-api"

# Install dependencies
pip install requests

# Dry run first
DRY_RUN=true python configure_keycloak_audience.py

# Apply changes
DRY_RUN=false python configure_keycloak_audience.py
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KEYCLOAK_URL` | `https://auth.stoa.cab-i.com` | Keycloak base URL |
| `KEYCLOAK_REALM` | `stoa` | Keycloak realm |
| `KEYCLOAK_ADMIN_USER` | `admin` | Admin username |
| `KEYCLOAK_ADMIN_PASS` | (required) | Admin password |
| `RESOURCE_SERVER_ID` | `control-plane-api` | Target audience |
| `CLIENTS_TO_CONFIGURE` | `control-plane-ui stoa-portal mcp-gateway-client` | Space-separated client IDs |
| `DRY_RUN` | `false` | Preview mode |

## Verification

### Step 1: Get a Token

```bash
# Using password grant (for testing only)
TOKEN=$(curl -s -X POST \
    'https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/token' \
    -d 'grant_type=password' \
    -d 'client_id=control-plane-ui' \
    -d 'username=your-user' \
    -d 'password=your-password' \
    -d 'scope=openid profile email' | jq -r '.access_token')
```

### Step 2: Decode and Verify

```bash
# Decode the token payload
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq '{aud, azp, iss}'
```

### Expected Output

```json
{
  "aud": "control-plane-api",
  "azp": "control-plane-ui",
  "iss": "https://auth.stoa.cab-i.com/realms/stoa"
}
```

### Step 3: Test API Access

```bash
# Test via Gateway
curl -H "Authorization: Bearer $TOKEN" \
    https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/health/live

# Test direct API
curl -H "Authorization: Bearer $TOKEN" \
    https://api.stoa.cab-i.com/health/live
```

## Manual Configuration (UI)

If you prefer to configure via Keycloak Admin Console:

1. Go to **Keycloak Admin Console** → **Clients** → **control-plane-ui**
2. Navigate to **Client scopes** tab
3. Click on **control-plane-ui-dedicated**
4. Go to **Mappers** tab
5. Click **Add mapper** → **By configuration**
6. Select **Audience**
7. Configure:
   - Name: `api-audience-mapper`
   - Included Client Audience: `control-plane-api`
   - Add to ID token: OFF
   - Add to access token: ON
8. Click **Save**
9. Repeat for `stoa-portal` and `mcp-gateway-client`

## Troubleshooting

### 401 Unauthorized

If you're getting 401 errors after configuration:

1. **Check token audience**:
   ```bash
   echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq '.aud'
   ```
   Should return `"control-plane-api"` or `["control-plane-api"]`

2. **Clear browser cache**: Old tokens might be cached

3. **Force re-authentication**: Log out and log back in

4. **Check Keycloak logs**: Look for mapper errors

### Mapper Not Applied

If the mapper isn't being applied:

1. Verify the mapper exists in Keycloak Admin Console
2. Check if the scope is assigned to the client
3. Ensure "Add to access token" is ON
4. Try creating the mapper at client level (not scope level)

## Related Files

| File | Purpose |
|------|---------|
| `deploy/platform-bootstrap/scripts/configure-keycloak-audience.sh` | Bash configuration script |
| `deploy/platform-bootstrap/scripts/configure_keycloak_audience.py` | Python configuration script |
| `deploy/platform-bootstrap/policies/jwt-validation.yaml` | Gateway JWT policy |
| `control-plane-api/src/auth/dependencies.py` | FastAPI JWT validation |

## References

- [RFC 7519 - JSON Web Token (JWT)](https://tools.ietf.org/html/rfc7519)
- [OAuth 2.0 Resource Indicators](https://tools.ietf.org/html/rfc8707)
- [Keycloak - Audience Support](https://www.keycloak.org/docs/latest/server_admin/#audience-support)
