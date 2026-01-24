#!/bin/bash
# =============================================================================
# Update Keycloak control-plane-ui client redirectURIs
# CAB-237: Rename devops.gostoa.dev → console.gostoa.dev
# =============================================================================
#
# This script updates the control-plane-ui client in Keycloak to use
# the new console.gostoa.dev domain instead of devops.gostoa.dev
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - Keycloak deployed in stoa-system namespace
#
# Usage:
#   ./update-keycloak-console-redirect.sh [BASE_DOMAIN]
#
# Example:
#   ./update-keycloak-console-redirect.sh gostoa.dev
# =============================================================================

set -e

# Configuration
BASE_DOMAIN="${1:-gostoa.dev}"
NAMESPACE="${KEYCLOAK_NAMESPACE:-stoa-system}"
REALM="${KEYCLOAK_REALM:-stoa}"
CLIENT_ID="control-plane-ui"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-demo}"

CONSOLE_URL="https://console.${BASE_DOMAIN}"

echo "=== Updating Keycloak Client: ${CLIENT_ID} ==="
echo "Namespace: ${NAMESPACE}"
echo "Realm: ${REALM}"
echo "New redirect URL: ${CONSOLE_URL}/*"
echo ""

# Get Keycloak pod
KEYCLOAK_POD=$(kubectl get pods -n ${NAMESPACE} -l app=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
               kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}')

if [ -z "${KEYCLOAK_POD}" ]; then
    echo "ERROR: Could not find Keycloak pod in namespace ${NAMESPACE}"
    exit 1
fi

echo "Found Keycloak pod: ${KEYCLOAK_POD}"

# Authenticate to Keycloak
echo ""
echo "=== Authenticating to Keycloak ==="
kubectl exec -n ${NAMESPACE} ${KEYCLOAK_POD} -- \
    /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user ${ADMIN_USER} \
    --password ${ADMIN_PASS}

# Get current client configuration
echo ""
echo "=== Current ${CLIENT_ID} configuration ==="
kubectl exec -n ${NAMESPACE} ${KEYCLOAK_POD} -- \
    /opt/keycloak/bin/kcadm.sh get clients \
    -r ${REALM} \
    --fields id,clientId,redirectUris,webOrigins \
    -q clientId=${CLIENT_ID}

# Get client ID (internal UUID)
CLIENT_UUID=$(kubectl exec -n ${NAMESPACE} ${KEYCLOAK_POD} -- \
    /opt/keycloak/bin/kcadm.sh get clients \
    -r ${REALM} \
    --fields id \
    -q clientId=${CLIENT_ID} \
    --format csv --noquotes | tail -1)

if [ -z "${CLIENT_UUID}" ]; then
    echo "ERROR: Could not find client ${CLIENT_ID} in realm ${REALM}"
    exit 1
fi

echo ""
echo "Client UUID: ${CLIENT_UUID}"

# Update redirectUris and webOrigins
echo ""
echo "=== Updating client redirectUris and webOrigins ==="
kubectl exec -n ${NAMESPACE} ${KEYCLOAK_POD} -- \
    /opt/keycloak/bin/kcadm.sh update clients/${CLIENT_UUID} \
    -r ${REALM} \
    -s "redirectUris=[\"${CONSOLE_URL}/*\",\"http://localhost:3000/*\",\"http://localhost:5173/*\"]" \
    -s "webOrigins=[\"${CONSOLE_URL}\",\"http://localhost:3000\",\"http://localhost:5173\"]"

# Verify update
echo ""
echo "=== Updated ${CLIENT_ID} configuration ==="
kubectl exec -n ${NAMESPACE} ${KEYCLOAK_POD} -- \
    /opt/keycloak/bin/kcadm.sh get clients \
    -r ${REALM} \
    --fields id,clientId,redirectUris,webOrigins \
    -q clientId=${CLIENT_ID}

echo ""
echo "=== SUCCESS ==="
echo "Client ${CLIENT_ID} updated with new redirectUris:"
echo "  - ${CONSOLE_URL}/*"
echo "  - http://localhost:3000/*"
echo "  - http://localhost:5173/*"
echo ""
echo "Note: If you also have an argocd client with SSO, update it similarly."
