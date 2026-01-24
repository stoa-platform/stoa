#!/bin/bash
# Setup Keycloak Authentication for Observability Stack
#
# This script:
# 1. Creates secrets for oauth2-proxy
# 2. Deploys oauth2-proxy for Prometheus and Loki
# 3. Updates Ingresses to use oauth2-proxy
# 4. Upgrades Grafana with OIDC config
#
# Prerequisites:
# - Keycloak client 'observability' created in realm 'stoa'
# - Client secret from Keycloak

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for required argument
if [ -z "$1" ]; then
  echo "Usage: $0 <KEYCLOAK_CLIENT_SECRET>"
  echo ""
  echo "Get the client secret from Keycloak:"
  echo "1. Go to https://auth.gostoa.dev"
  echo "2. Login and select realm 'stoa'"
  echo "3. Go to Clients > observability > Credentials"
  echo "4. Copy the Client Secret"
  exit 1
fi

CLIENT_SECRET="$1"
COOKIE_SECRET=$(openssl rand -base64 32 | tr -- '+/' '-_')

echo "=== Setting up Keycloak Authentication for Observability ==="
echo ""

# Step 1: Create secrets
echo "Step 1: Creating oauth2-proxy secrets..."

kubectl create secret generic oauth2-proxy-secret -n stoa-monitoring \
  --from-literal=cookie-secret="$COOKIE_SECRET" \
  --from-literal=client-secret="$CLIENT_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic oauth2-proxy-secret -n stoa-system \
  --from-literal=cookie-secret="$COOKIE_SECRET" \
  --from-literal=client-secret="$CLIENT_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secrets created."

# Step 2: Create Grafana OIDC secret
echo "Step 2: Creating Grafana OIDC secret..."

kubectl create secret generic grafana-oidc-secret -n stoa-monitoring \
  --from-literal=GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET="$CLIENT_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Grafana secret created."

# Step 3: Deploy oauth2-proxy for Prometheus
echo "Step 3: Deploying oauth2-proxy for Prometheus..."
kubectl apply -f "$SCRIPT_DIR/oauth2-proxy-prometheus.yaml"

# Step 4: Deploy oauth2-proxy for Loki
echo "Step 4: Deploying oauth2-proxy for Loki..."
kubectl apply -f "$SCRIPT_DIR/oauth2-proxy-loki.yaml"

# Step 5: Wait for oauth2-proxy pods
echo "Step 5: Waiting for oauth2-proxy pods..."
kubectl wait --for=condition=ready pod -l app=oauth2-proxy-prometheus -n stoa-monitoring --timeout=120s || true
kubectl wait --for=condition=ready pod -l app=oauth2-proxy-loki -n stoa-system --timeout=120s || true

# Step 6: Update Ingresses
echo "Step 6: Updating Ingresses..."
kubectl apply -f "$SCRIPT_DIR/prometheus-ingress.yaml"

# For Loki, delete the Helm-managed ingress first if it exists
kubectl delete ingress stoa-platform-loki -n stoa-system --ignore-not-found=true
kubectl apply -f "$SCRIPT_DIR/loki-ingress.yaml"

# Step 7: Upgrade Grafana with OIDC
echo "Step 7: Upgrading Grafana with OIDC configuration..."
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n stoa-monitoring \
  -f "$SCRIPT_DIR/values-grafana-oidc.yaml" \
  --reuse-values

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Keycloak authentication is now enabled for:"
echo "  - Grafana:    https://grafana.gostoa.dev (native OIDC)"
echo "  - Prometheus: https://prometheus.gostoa.dev (via oauth2-proxy)"
echo "  - Loki:       https://loki.gostoa.dev (via oauth2-proxy)"
echo ""
echo "Users can login with their Keycloak credentials (e.g., admin@cab-i.com)"
echo ""
echo "Note: Grafana also keeps local admin login available."
echo "      Get admin password: kubectl get secret -n stoa-monitoring kube-prometheus-stack-grafana -o jsonpath='{.data.admin-password}' | base64 -d"
