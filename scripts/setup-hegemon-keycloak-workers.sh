#!/bin/bash
# Create Keycloak Service Accounts for HEGEMON Workers
#
# Usage: ./scripts/setup-hegemon-keycloak-workers.sh [--dry-run]
#
# Creates 5 service account clients (hegemon-worker-{role}) with custom JWT claims:
#   - worker_name: hardcoded mapper (value = role name)
#   - worker_roles: hardcoded mapper (value = JSON array of roles)
#
# Each client uses client_credentials flow with 5-min access token TTL.
# Client secrets belong in OpenBao at secret/stoa/tooling/hegemon/worker-{role},
# field KC_CLIENT_SECRET. Tooling tokens are read-only (ADR-075), so an operator
# stores them with put-secret; this script never prints them.
#
# Prerequisites:
#   - kubectl access to stoa-system namespace
#   - Keycloak admin password (auto-retrieved from K8s secret)
#
# CAB-1712: HEGEMON Keycloak service accounts

set -euo pipefail
set +x
# shellcheck source=scripts/lib/secret-input.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/lib/secret-input.sh"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "[DRY-RUN] No changes will be made"
fi

REALM="stoa"
WORKERS=("backend" "frontend" "auth" "mcp" "qa")

# --- Keycloak Admin Auth ---

KEYCLOAK_POD=$(kubectl get pods -n stoa-system -l app=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -z "$KEYCLOAK_POD" ]]; then
  KEYCLOAK_POD=$(kubectl get pods -n stoa-system -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
fi
if [[ -z "$KEYCLOAK_POD" ]]; then
  echo "ERROR: Keycloak pod not found in stoa-system"
  exit 1
fi
echo "Using Keycloak pod: $KEYCLOAK_POD"

KEYCLOAK_ADMIN_PASSWORD=$(kubectl get secret keycloak -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d)
if [[ -z "$KEYCLOAK_ADMIN_PASSWORD" ]]; then
  echo "ERROR: Could not retrieve Keycloak admin password"
  exit 1
fi

KCADM="kubectl exec -n stoa-system $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh"

echo "Logging into Keycloak..."
printf '%s\n' "$KEYCLOAK_ADMIN_PASSWORD" | kubectl exec -i -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user admin

echo ""
echo "=== Creating HEGEMON Worker Service Accounts ==="
echo ""

for ROLE in "${WORKERS[@]}"; do
  CLIENT_ID="hegemon-worker-${ROLE}"
  echo "--- Processing: $CLIENT_ID ---"

  # Check if client already exists.
  EXISTING=$($KCADM get clients -r "$REALM" --fields clientId 2>/dev/null | grep -c "\"$CLIENT_ID\"" || echo "0")

  if [[ "$EXISTING" != "0" ]]; then
    echo "  Client already exists, updating mappers..."
    CLIENT_UUID=$($KCADM get clients -r "$REALM" --fields id,clientId 2>/dev/null \
      | grep -B1 "\"$CLIENT_ID\"" | grep '"id"' | cut -d'"' -f4)
  else
    if $DRY_RUN; then
      echo "  [DRY-RUN] Would create client: $CLIENT_ID"
      continue
    fi

    echo "  Creating client..."
    $KCADM create clients -r "$REALM" \
      -s clientId="$CLIENT_ID" \
      -s name="HEGEMON Worker (${ROLE})" \
      -s description="Service account for HEGEMON ${ROLE} worker" \
      -s enabled=true \
      -s protocol=openid-connect \
      -s publicClient=false \
      -s standardFlowEnabled=false \
      -s implicitFlowEnabled=false \
      -s directAccessGrantsEnabled=false \
      -s serviceAccountsEnabled=true \
      -s 'defaultClientScopes=["openid","profile","email"]' \
      -s 'attributes={"access.token.lifespan":"300"}'

    CLIENT_UUID=$($KCADM get clients -r "$REALM" --fields id,clientId 2>/dev/null \
      | grep -B1 "\"$CLIENT_ID\"" | grep '"id"' | cut -d'"' -f4)
    echo "  Client UUID: $CLIENT_UUID"
  fi

  if $DRY_RUN; then
    echo "  [DRY-RUN] Would add mappers for: $CLIENT_ID"
    continue
  fi

  # --- Protocol Mappers ---

  # worker_name: hardcoded claim with role name
  echo "  Adding worker_name mapper..."
  $KCADM create "clients/$CLIENT_UUID/protocol-mappers/models" -r "$REALM" \
    -s name=worker_name \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-hardcoded-claim-mapper \
    -s 'config={"claim.name":"worker_name","claim.value":"'"$ROLE"'","jsonType.label":"String","id.token.claim":"true","access.token.claim":"true","userinfo.token.claim":"false"}' \
    2>/dev/null || echo "    (mapper may already exist)"

  # worker_roles: hardcoded claim with JSON array
  echo "  Adding worker_roles mapper..."
  $KCADM create "clients/$CLIENT_UUID/protocol-mappers/models" -r "$REALM" \
    -s name=worker_roles \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-hardcoded-claim-mapper \
    -s 'config={"claim.name":"worker_roles","claim.value":"[\"'"$ROLE"'\"]","jsonType.label":"JSON","id.token.claim":"true","access.token.claim":"true","userinfo.token.claim":"false"}' \
    2>/dev/null || echo "    (mapper may already exist)"

  # --- Extract and Store Secret ---

  CLIENT_SECRET=$($KCADM get "clients/$CLIENT_UUID/client-secret" -r "$REALM" --fields value 2>/dev/null \
    | grep '"value"' | cut -d'"' -f4)

  if [[ -z "$CLIENT_SECRET" ]]; then
    echo "  ERROR: Could not retrieve client secret for $CLIENT_ID"
    continue
  fi

  echo "  Client secret retrieved. Store it with put-secret in OpenBao at"
  echo "  secret/stoa/tooling/hegemon/worker-${ROLE} (field KC_CLIENT_SECRET)."
  echo "See docs/runbooks/first-admin-bootstrap.md for stdin-based secret storage."

  echo ""
done

# --- Verification ---

echo "=== Verification ==="
echo ""
for ROLE in "${WORKERS[@]}"; do
  CLIENT_ID="hegemon-worker-${ROLE}"
  if $DRY_RUN; then
    echo "  [DRY-RUN] Would verify: $CLIENT_ID"
    continue
  fi

  # Get client secret for verification.
  CLIENT_UUID=$($KCADM get clients -r "$REALM" --fields id,clientId 2>/dev/null \
    | grep -B1 "\"$CLIENT_ID\"" | grep '"id"' | cut -d'"' -f4)
  CLIENT_SECRET=$($KCADM get "clients/$CLIENT_UUID/client-secret" -r "$REALM" --fields value 2>/dev/null \
    | grep '"value"' | cut -d'"' -f4)

  # Get token endpoint from KC.
  KC_URL=$(kubectl get ingress -n stoa-system -o jsonpath='{.items[0].spec.rules[0].host}' 2>/dev/null || echo "auth.gostoa.dev")
  TOKEN_URL="https://${KC_URL}/realms/${REALM}/protocol/openid-connect/token"

  TOKEN_RESPONSE=$(curl -s -X POST "$TOKEN_URL" \
    -d "client_id=$CLIENT_ID" \
    --data-urlencode "client_secret=$CLIENT_SECRET" \
    -d "grant_type=client_credentials" 2>/dev/null)

  ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

  if [[ -z "$ACCESS_TOKEN" ]]; then
    echo "  FAIL: $CLIENT_ID — could not get token"
    echo "    Request failed; response details are withheld."
    continue
  fi

  # Decode JWT payload and check claims.
  PAYLOAD=$(echo "$ACCESS_TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null || echo "$ACCESS_TOKEN" | cut -d. -f2 | base64 -D 2>/dev/null)
  WORKER_NAME=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('worker_name','MISSING'))" 2>/dev/null)
  WORKER_ROLES=$(echo "$PAYLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('worker_roles','MISSING'))" 2>/dev/null)

  if [[ "$WORKER_NAME" == "$ROLE" ]]; then
    echo "  OK: $CLIENT_ID — worker_name=$WORKER_NAME, worker_roles=$WORKER_ROLES"
  else
    echo "  FAIL: $CLIENT_ID — worker_name=$WORKER_NAME (expected $ROLE)"
  fi
done

echo ""
echo "=== Done ==="
