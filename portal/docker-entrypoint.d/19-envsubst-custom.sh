#!/bin/sh
# Custom envsubst that only substitutes our variables (not nginx $uri, $host, etc.)
# Runs BEFORE the built-in 20-envsubst-on-templates.sh (which has nothing to process).
# Template is in /etc/nginx/custom-templates/ (not /etc/nginx/templates/).
set -e

# 1. Nginx backend proxy config
envsubst '${API_BACKEND_URL} ${DNS_RESOLVER}' \
  < /etc/nginx/custom-templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

# 2. Runtime config for the SPA — overrides Vite build-time defaults
#    These env vars come from K8s deployment.yaml or docker-compose.yml
#    Empty values are ignored by the app (falls back to build-time defaults)
cat > /usr/share/nginx/html/runtime-config.js <<EOF
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
};
EOF

# 3. Cache-bust runtime-config.js URL in index.html
#    index.html is served with Cache-Control: no-cache so browsers revalidate on every load.
#    Replacing __RUNTIME_CFG_V__ with a fresh value on each pod boot forces any browser
#    holding a stale /runtime-config.js (previously cached with immutable) to fetch the
#    new URL and get the current config. Uses pod start time so the value changes on rollout.
RUNTIME_CFG_V="$(date -u +%Y%m%d%H%M%S)"
sed -i "s|__RUNTIME_CFG_V__|${RUNTIME_CFG_V}|g" /usr/share/nginx/html/index.html
