#!/bin/bash
# Create Keycloak Admin Client for Control-Plane API Service Account Management
#
# Usage: ./setup-keycloak-admin-client.sh <KEYCLOAK_ADMIN_PASSWORD>
#
# This script creates the 'control-plane-api-admin' client with:
# - Service account enabled (for client credentials flow)
# - realm-management roles for creating/managing clients
#
# The client secret is then stored in the control-plane-api-secrets

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <KEYCLOAK_ADMIN_PASSWORD>"
  echo ""
  echo "Get the admin password from: kubectl get secret keycloak -n stoa-system -o jsonpath='{.data.admin-password}' | base64 -d"
  exit 1
fi

KEYCLOAK_ADMIN_PASSWORD="$1"
CLIENT_ID_NAME="control-plane-api-admin"

# Find Keycloak pod
KEYCLOAK_POD=$(kubectl get pods -n stoa-system -l app=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -z "$KEYCLOAK_POD" ]; then
  KEYCLOAK_POD=$(kubectl get pods -n stoa-system -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
fi

if [ -z "$KEYCLOAK_POD" ]; then
  echo "ERROR: Keycloak pod not found"
  exit 1
fi

echo "=== Creating Keycloak Admin Client for Service Account Management ==="
echo "Using Keycloak pod: $KEYCLOAK_POD"

# Login to Keycloak
echo "Logging into Keycloak..."
kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user admin \
  --password "$KEYCLOAK_ADMIN_PASSWORD"

# Check if client already exists
echo "Checking if client '$CLIENT_ID_NAME' exists..."
EXISTING=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields clientId 2>/dev/null | grep -c "\"$CLIENT_ID_NAME\"" || echo "0")

if [ "$EXISTING" != "0" ]; then
  echo "Client '$CLIENT_ID_NAME' already exists. Getting client ID..."
  CLIENT_UUID=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields id,clientId 2>/dev/null | grep -B1 "\"$CLIENT_ID_NAME\"" | grep '"id"' | cut -d'"' -f4)
else
  echo "Creating client '$CLIENT_ID_NAME'..."

  # Create the admin client with service account enabled
  kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh create clients -r stoa \
    -s clientId="$CLIENT_ID_NAME" \
    -s name="Control Plane API Admin" \
    -s description="Admin client for Service Account management" \
    -s enabled=true \
    -s protocol=openid-connect \
    -s publicClient=false \
    -s standardFlowEnabled=false \
    -s implicitFlowEnabled=false \
    -s directAccessGrantsEnabled=false \
    -s serviceAccountsEnabled=true \
    -s 'defaultClientScopes=["openid","profile","email"]'

  echo "Client created successfully"

  # Get the client UUID
  CLIENT_UUID=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields id,clientId 2>/dev/null | grep -B1 "\"$CLIENT_ID_NAME\"" | grep '"id"' | cut -d'"' -f4)
fi

echo "Client UUID: $CLIENT_UUID"

# Get service account user ID
echo "Getting service account user..."
SA_USER_ID=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get "clients/$CLIENT_UUID/service-account-user" -r stoa --fields id 2>/dev/null | grep '"id"' | cut -d'"' -f4)
echo "Service account user ID: $SA_USER_ID"

# Get realm-management client ID
echo "Getting realm-management client..."
REALM_MGMT_CLIENT=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get clients -r stoa --fields id,clientId 2>/dev/null | grep -B1 '"realm-management"' | grep '"id"' | cut -d'"' -f4)
echo "realm-management client ID: $REALM_MGMT_CLIENT"

# Assign required client roles for managing clients
echo "Assigning realm-management roles to service account..."

# Roles needed for creating and managing clients
ROLES_TO_ASSIGN="manage-clients view-clients manage-users view-users"

for ROLE_NAME in $ROLES_TO_ASSIGN; do
  echo "  - Assigning role: $ROLE_NAME"
  kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh add-roles -r stoa \
    --uusername "service-account-$CLIENT_ID_NAME" \
    --cclientid realm-management \
    --rolename "$ROLE_NAME" 2>/dev/null || echo "    (role may already be assigned)"
done

# Get the client secret
echo ""
echo "Getting client secret..."
CLIENT_SECRET=$(kubectl exec -n stoa-system "$KEYCLOAK_POD" -- /opt/keycloak/bin/kcadm.sh get "clients/$CLIENT_UUID/client-secret" -r stoa --fields value 2>/dev/null | grep '"value"' | cut -d'"' -f4)

if [ -z "$CLIENT_SECRET" ]; then
  echo "ERROR: Could not retrieve client secret"
  exit 1
fi

echo ""
echo "=== Admin Client Created Successfully ==="
echo ""
echo "Client ID: $CLIENT_ID_NAME"
echo "Client Secret: $CLIENT_SECRET"
echo ""

# Update the Kubernetes secret
echo "Updating control-plane-api-secrets..."
SECRET_BASE64=$(echo -n "$CLIENT_SECRET" | base64)

kubectl patch secret control-plane-api-secrets -n stoa-system --type='json' \
  -p="[{\"op\": \"replace\", \"path\": \"/data/KEYCLOAK_ADMIN_CLIENT_SECRET\", \"value\": \"$SECRET_BASE64\"}]"

echo ""
echo "=== Secret Updated ==="
echo ""
echo "Now restart the control-plane-api to pick up the new secret:"
echo ""
echo "  kubectl rollout restart deployment/control-plane-api -n stoa-system"
echo ""
