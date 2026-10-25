#!/bin/bash
# Create Keycloak Client for Observability Stack
#
# Usage: KEYCLOAK_ADMIN_PASSWORD from the environment; no positional arguments.
#
# This script creates the 'observability' client in Keycloak with proper redirect URIs

# Optional origins (absolute URLs without a trailing slash):
# GRAFANA_ORIGIN defaults to http://localhost:3001.
# PROMETHEUS_ORIGIN defaults to http://localhost:9090.
# LOKI_ORIGIN defaults to http://localhost:3100.
set -euo pipefail
set +x

GRAFANA_ORIGIN="${GRAFANA_ORIGIN:-http://localhost:3001}"
PROMETHEUS_ORIGIN="${PROMETHEUS_ORIGIN:-http://localhost:9090}"
LOKI_ORIGIN="${LOKI_ORIGIN:-http://localhost:3100}"

if [ $# -ne 0 ]; then
  echo "Positional credentials are unsupported; use KEYCLOAK_ADMIN_PASSWORD." >&2
  exit 2
fi
: "${KEYCLOAK_ADMIN_PASSWORD:?An explicit admin password is required}"

KEYCLOAK_POD=$(kubectl get pods -n stoa-system -l app=keycloak -o jsonpath='{.items[0].metadata.name}')

if [ -z "$KEYCLOAK_POD" ]; then
  echo "ERROR: Keycloak pod not found"
  exit 1
fi

echo "=== Creating Keycloak Client for Observability ==="
echo "Using Keycloak pod: $KEYCLOAK_POD"

# Login to Keycloak
echo "Logging into Keycloak..."
printf '%s\n' "$KEYCLOAK_ADMIN_PASSWORD" | kubectl exec -i -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user admin

# Check if client already exists in stoa realm
echo "Checking if client 'observability' exists..."
EXISTING=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields clientId 2>/dev/null | grep -c '"observability"' || true)

if [ "$EXISTING" != "0" ]; then
  echo "Client 'observability' already exists. Getting client ID..."
  CLIENT_ID=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields id,clientId 2>/dev/null | grep -B1 '"observability"' | grep '"id"' | cut -d'"' -f4)
  echo "Client ID: $CLIENT_ID"
else
  echo "Creating client 'observability'..."

  # Create the client
  kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh create clients -r stoa \
    -s clientId=observability \
    -s name="Observability Stack" \
    -s description="OIDC client for Grafana, Prometheus, and Loki" \
    -s enabled=true \
    -s protocol=openid-connect \
    -s publicClient=false \
    -s standardFlowEnabled=true \
    -s implicitFlowEnabled=false \
    -s directAccessGrantsEnabled=false \
    -s serviceAccountsEnabled=false \
    -s "redirectUris=[\"${GRAFANA_ORIGIN}/login/generic_oauth\",\"${PROMETHEUS_ORIGIN}/oauth2/callback\",\"${LOKI_ORIGIN}/oauth2/callback\"]" \
    -s 'webOrigins=["+"]' \
    -s 'defaultClientScopes=["openid","profile","email","roles"]'

  echo "Client created successfully"

  # Get the client ID
  CLIENT_ID=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields id,clientId 2>/dev/null | grep -B1 '"observability"' | grep '"id"' | cut -d'"' -f4)
fi

# Get the client secret
echo "Getting client secret..."
CLIENT_SECRET=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get "clients/$CLIENT_ID/client-secret" -r stoa --fields value 2>/dev/null | grep '"value"' | cut -d'"' -f4)

if [ -z "$CLIENT_SECRET" ]; then
  echo "ERROR: Could not retrieve client secret"
  exit 1
fi

echo ""
echo "=== Client Created Successfully ==="
echo ""
echo "Client ID: observability"
echo "Sensitive values are withheld; use the approved secret store."
echo ""
echo "Now run the setup script with this secret:"
echo ""
echo "Sensitive values are withheld; use the approved secret store."
