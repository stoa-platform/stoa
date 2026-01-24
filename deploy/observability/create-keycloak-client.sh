#!/bin/bash
# Create Keycloak Client for Observability Stack
#
# Usage: ./create-keycloak-client.sh <KEYCLOAK_ADMIN_PASSWORD>
#
# This script creates the 'observability' client in Keycloak with proper redirect URIs

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <KEYCLOAK_ADMIN_PASSWORD>"
  echo ""
  echo "Get the admin password from AWS Secrets Manager or check the Keycloak deployment"
  exit 1
fi

KEYCLOAK_ADMIN_PASSWORD="$1"
KEYCLOAK_POD=$(kubectl get pods -n stoa-system -l app=keycloak -o jsonpath='{.items[0].metadata.name}')

if [ -z "$KEYCLOAK_POD" ]; then
  echo "ERROR: Keycloak pod not found"
  exit 1
fi

echo "=== Creating Keycloak Client for Observability ==="
echo "Using Keycloak pod: $KEYCLOAK_POD"

# Login to Keycloak
echo "Logging into Keycloak..."
kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user admin \
  --password "$KEYCLOAK_ADMIN_PASSWORD"

# Check if client already exists in stoa realm
echo "Checking if client 'observability' exists..."
EXISTING=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields clientId 2>/dev/null | grep -c '"observability"' || echo "0")

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
    -s directAccessGrantsEnabled=true \
    -s serviceAccountsEnabled=false \
    -s 'redirectUris=["https://grafana.gostoa.dev/*","https://prometheus.gostoa.dev/oauth2/callback","https://loki.gostoa.dev/oauth2/callback"]' \
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
echo "Client Secret: $CLIENT_SECRET"
echo ""
echo "Now run the setup script with this secret:"
echo ""
echo "  ./deploy/observability/setup-keycloak-auth.sh $CLIENT_SECRET"
