#!/bin/sh
# Custom envsubst that only substitutes our variables (not nginx $uri, $host, etc.)
# Runs BEFORE the built-in 20-envsubst-on-templates.sh (which has nothing to process).
# Template is in /etc/nginx/custom-templates/ (not /etc/nginx/templates/).
set -e

# 1. Nginx backend proxy config
envsubst '${API_BACKEND_URL} ${LOGS_BACKEND_URL} ${GRAFANA_BACKEND_URL} ${PROMETHEUS_BACKEND_URL} ${DNS_RESOLVER}' \
  < /etc/nginx/custom-templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

# 2. Runtime config for the SPA — overrides Vite build-time defaults
#    These env vars come from K8s deployment.yaml or docker-compose.yml
cat > /usr/share/nginx/html/runtime-config.js <<EOF
window.__STOA_RUNTIME__ = {
  VITE_KEYCLOAK_URL: "${VITE_KEYCLOAK_URL:-}",
  VITE_KEYCLOAK_REALM: "${VITE_KEYCLOAK_REALM:-}",
  VITE_KEYCLOAK_CLIENT_ID: "${VITE_KEYCLOAK_CLIENT_ID:-}",
  VITE_API_URL: "${VITE_API_URL:-}",
  VITE_BASE_DOMAIN: "${VITE_BASE_DOMAIN:-}",
  VITE_ENVIRONMENT: "${VITE_ENVIRONMENT:-}",
  VITE_GATEWAY_URL: "${VITE_GATEWAY_URL:-}",
  VITE_MCP_GATEWAY_URL: "${VITE_MCP_GATEWAY_URL:-}",
  VITE_PORTAL_URL: "${VITE_PORTAL_URL:-}",
  VITE_GRAFANA_URL: "${VITE_GRAFANA_URL:-}",
  VITE_ARGOCD_URL: "${VITE_ARGOCD_URL:-}",
};
EOF
