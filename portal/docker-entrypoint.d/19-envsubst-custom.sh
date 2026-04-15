#!/bin/sh
set -e

# 1. Nginx backend proxy config
envsubst '${API_BACKEND_URL} ${DNS_RESOLVER}' \
  < /etc/nginx/custom-templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

# 2. Runtime config for the SPA — overrides Vite build-time defaults.
#    Env vars come from K8s deployment.yaml, docker-compose.yml, or k3d configmap.
#    Empty values are ignored by config.ts (falls back to build-time or hardcoded default).
# Written to /tmp (not /usr/share/nginx/html) for readOnlyRootFilesystem compatibility.
# nginx.conf serves /runtime-config.js from /tmp/runtime-config.js.
cat > /tmp/runtime-config.js <<EOF
window.__STOA_RUNTIME__ = {
  VITE_KEYCLOAK_URL: "${VITE_KEYCLOAK_URL:-}",
  VITE_KEYCLOAK_REALM: "${VITE_KEYCLOAK_REALM:-}",
  VITE_KEYCLOAK_CLIENT_ID: "${VITE_KEYCLOAK_CLIENT_ID:-}",
  VITE_API_URL: "${VITE_API_URL:-}",
  VITE_MCP_URL: "${VITE_MCP_URL:-}",
  VITE_BASE_DOMAIN: "${VITE_BASE_DOMAIN:-}",
  VITE_ENVIRONMENT: "${VITE_ENVIRONMENT:-}",
  VITE_CONSOLE_URL: "${VITE_CONSOLE_URL:-}",
  VITE_DOCS_URL: "${VITE_DOCS_URL:-}",
  VITE_GRAFANA_URL: "${VITE_GRAFANA_URL:-}",
};
EOF
