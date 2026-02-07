#!/bin/sh
# Custom envsubst that only substitutes our variables (not nginx $uri, $host, etc.)
# Runs BEFORE the built-in 20-envsubst-on-templates.sh (which has nothing to process).
# Template is in /etc/nginx/custom-templates/ (not /etc/nginx/templates/).
set -e
envsubst '${API_BACKEND_URL} ${LOGS_BACKEND_URL} ${GRAFANA_BACKEND_URL} ${DNS_RESOLVER}' \
  < /etc/nginx/custom-templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf
