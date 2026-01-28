# STOA Demo - Authentication Model

## Warning: Demo Mode Notice

This demo instance (`demo.gostoa.dev`) runs with **authentication disabled** for demonstration purposes.

**DO NOT use this configuration in production.**

---

## Demo Configuration

| Setting | Value | Note |
|---------|-------|------|
| `AUTH_ENABLED` | `false` | Bypasses all auth checks |
| `DEMO_MODE` | `true` | Enables demo triggers |
| `DEMO_SCENARIOS_ENABLED` | `true` | Enables `/demo/*` endpoints |

---

## Production Authentication

In production, STOA supports two authentication methods:

### 1. JWT Bearer Token

```bash
curl -X POST https://api.gostoa.dev/v1/transactions/score \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN-001",...}'
```

**JWT Claims Required:**
- `sub`: User/service identifier
- `aud`: `stoa-platform`
- `scope`: `fraud:read`, `settlement:write`, `sanctions:read`
- `exp`: Expiration timestamp

**Issuer:** Keycloak (`auth.gostoa.dev`)

### 2. API Key

```bash
curl -X POST https://api.gostoa.dev/v1/transactions/score \
  -H "X-API-Key: <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TXN-001",...}'
```

**API Key Format:** `stoa_<environment>_<random_32_chars>`

**Rate Limits by Key Type:**

| Key Type | Rate Limit |
|----------|------------|
| Standard | 100 req/min |
| Premium | 1000 req/min |
| Enterprise | Unlimited |

---

## Keycloak Realm Configuration

| Setting | Value |
|---------|-------|
| Realm | `stoa` |
| Client ID | `stoa-api` |
| Client Protocol | `openid-connect` |
| Access Type | `confidential` |

---

## Enabling Auth in Demo

To test with authentication enabled:

```bash
# Set env vars
export AUTH_ENABLED=true
export KEYCLOAK_URL=https://auth.gostoa.dev
export KEYCLOAK_REALM=stoa

# Restart with auth
helm upgrade stoa-demo ./charts/stoa-platform \
  -n stoa-system \
  --set mockBackends.env.AUTH_ENABLED=true
```

---

## Security Contacts

- **Security Issues:** security@gostoa.dev
- **API Access Requests:** api-access@gostoa.dev
