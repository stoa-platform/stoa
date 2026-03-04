# HEGEMON Worker Keycloak Setup

## Overview

Each HEGEMON worker authenticates to the STOA Gateway using Keycloak service accounts.
This runbook documents the setup of 5 worker clients + 1 realm role.

## Prerequisites

- Keycloak admin access on `auth.gostoa.dev` (realm: `stoa`)
- Infisical CLI configured (`infisical login`)
- `curl` + `jq` installed

## Architecture

```
Worker-1 ──► JWT (hegemon-worker-1) ──► STOA Gateway Internal (8090)
Worker-2 ──► JWT (hegemon-worker-2) ──►     validates JWT + role
Worker-3 ──► JWT (hegemon-worker-3) ──►     enforces supervision tier
Worker-4 ──► JWT (hegemon-worker-4) ──►     proxies to upstream
Worker-5 ──► JWT (hegemon-worker-5) ──►
```

## Step 1: Create Realm Role

Create the `hegemon-worker` role in the `stoa` realm.

```bash
# Get admin token
KC_URL="https://auth.gostoa.dev"
KC_TOKEN=$(curl -s -X POST "${KC_URL}/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=${KC_ADMIN_PASSWORD}" \
  -d "grant_type=password" | jq -r '.access_token')

# Create realm role
curl -s -X POST "${KC_URL}/admin/realms/stoa/roles" \
  -H "Authorization: Bearer ${KC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hegemon-worker",
    "description": "HEGEMON worker service account role — grants access to STOA Gateway internal endpoints"
  }'
```

## Step 2: Create 5 Worker Service Account Clients

Each worker gets its own client for independent credential rotation and audit trail.

```bash
for i in $(seq 1 5); do
  CLIENT_ID="hegemon-worker-${i}"

  # Create confidential client with service account
  curl -s -X POST "${KC_URL}/admin/realms/stoa/clients" \
    -H "Authorization: Bearer ${KC_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"clientId\": \"${CLIENT_ID}\",
      \"name\": \"HEGEMON Worker ${i}\",
      \"description\": \"Service account for HEGEMON worker-${i} VPS\",
      \"enabled\": true,
      \"clientAuthenticatorType\": \"client-secret\",
      \"serviceAccountsEnabled\": true,
      \"directAccessGrantsEnabled\": false,
      \"publicClient\": false,
      \"protocol\": \"openid-connect\",
      \"defaultClientScopes\": [\"openid\", \"profile\", \"email\"],
      \"optionalClientScopes\": [\"stoa:read\", \"stoa:write\"]
    }"

  echo "Created client: ${CLIENT_ID}"
done
```

## Step 3: Assign Role to Service Accounts

```bash
# Get role ID
ROLE_ID=$(curl -s "${KC_URL}/admin/realms/stoa/roles/hegemon-worker" \
  -H "Authorization: Bearer ${KC_TOKEN}" | jq -r '.id')

for i in $(seq 1 5); do
  CLIENT_ID="hegemon-worker-${i}"

  # Get client internal UUID
  CLIENT_UUID=$(curl -s "${KC_URL}/admin/realms/stoa/clients?clientId=${CLIENT_ID}" \
    -H "Authorization: Bearer ${KC_TOKEN}" | jq -r '.[0].id')

  # Get service account user ID
  SA_USER_ID=$(curl -s "${KC_URL}/admin/realms/stoa/clients/${CLIENT_UUID}/service-account-user" \
    -H "Authorization: Bearer ${KC_TOKEN}" | jq -r '.id')

  # Assign realm role to service account
  curl -s -X POST "${KC_URL}/admin/realms/stoa/users/${SA_USER_ID}/role-mappings/realm" \
    -H "Authorization: Bearer ${KC_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "[{\"id\": \"${ROLE_ID}\", \"name\": \"hegemon-worker\"}]"

  echo "Assigned hegemon-worker role to ${CLIENT_ID}"
done
```

## Step 4: Extract Client Secrets and Store in Infisical

```bash
for i in $(seq 1 5); do
  CLIENT_ID="hegemon-worker-${i}"

  # Get client UUID
  CLIENT_UUID=$(curl -s "${KC_URL}/admin/realms/stoa/clients?clientId=${CLIENT_ID}" \
    -H "Authorization: Bearer ${KC_TOKEN}" | jq -r '.[0].id')

  # Get client secret
  SECRET=$(curl -s "${KC_URL}/admin/realms/stoa/clients/${CLIENT_UUID}/client-secret" \
    -H "Authorization: Bearer ${KC_TOKEN}" | jq -r '.value')

  # Store in Infisical
  infisical secrets set "CLIENT_SECRET=${SECRET}" \
    --env=prod --path="/hegemon/worker-${i}"

  echo "Stored secret for ${CLIENT_ID} in Infisical prod/hegemon/worker-${i}/CLIENT_SECRET"
done
```

## Step 5: Verify JWT Token Acquisition

Test that each worker can obtain a JWT via `client_credentials` grant:

```bash
for i in $(seq 1 5); do
  CLIENT_ID="hegemon-worker-${i}"

  # Retrieve secret from Infisical
  SECRET=$(infisical secrets get CLIENT_SECRET --env=prod --path="/hegemon/worker-${i}" --plain)

  # Request token
  RESPONSE=$(curl -s -X POST "${KC_URL}/realms/stoa/protocol/openid-connect/token" \
    -d "client_id=${CLIENT_ID}" \
    -d "client_secret=${SECRET}" \
    -d "grant_type=client_credentials" \
    -d "scope=openid stoa:read stoa:write")

  TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')

  if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
    echo "FAIL: ${CLIENT_ID} — $(echo "$RESPONSE" | jq -r '.error_description')"
  else
    # Decode JWT and verify role
    ROLES=$(echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq -r '.realm_access.roles[]' 2>/dev/null)
    if echo "$ROLES" | grep -q "hegemon-worker"; then
      echo "OK: ${CLIENT_ID} — JWT obtained, hegemon-worker role present"
    else
      echo "WARN: ${CLIENT_ID} — JWT obtained but hegemon-worker role MISSING"
    fi
  fi
done
```

## Verification Checklist

- [ ] 5 clients created in Keycloak realm `stoa`
- [ ] Each client obtains a JWT via `client_credentials`
- [ ] JWT contains `realm_access.roles: ["hegemon-worker"]`
- [ ] Secrets stored in Infisical `prod/hegemon/worker-{N}/CLIENT_SECRET`

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `invalid_client` | Wrong client secret | Re-extract from KC and update Infisical |
| `unauthorized_client` | `serviceAccountsEnabled` is false | Edit client in KC admin UI |
| Missing `hegemon-worker` role in JWT | Role not assigned to service account | Re-run Step 3 |
| `invalid_scope` | Client scopes not configured | Add `stoa:read`/`stoa:write` to client scopes in KC |

## Rotation

To rotate a worker's client secret:

```bash
# Generate new secret in Keycloak
CLIENT_UUID=$(curl -s "${KC_URL}/admin/realms/stoa/clients?clientId=hegemon-worker-${N}" \
  -H "Authorization: Bearer ${KC_TOKEN}" | jq -r '.[0].id')
NEW_SECRET=$(curl -s -X POST "${KC_URL}/admin/realms/stoa/clients/${CLIENT_UUID}/client-secret" \
  -H "Authorization: Bearer ${KC_TOKEN}" | jq -r '.value')

# Update in Infisical
infisical secrets set "CLIENT_SECRET=${NEW_SECRET}" --env=prod --path="/hegemon/worker-${N}"

# Restart the worker's hegemon-agent service
ssh hegemon@worker-${N} "sudo systemctl restart hegemon-agent"
```
