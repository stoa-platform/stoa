#!/bin/sh
set -e
envsubst '${API_BACKEND_URL} ${DNS_RESOLVER}' \
  < /etc/nginx/custom-templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf
