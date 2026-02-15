#!/usr/bin/env bash
# Register httpbin proxy route on STOA gateway for Arena benchmarks.
# Same backend as Kong/Gravitee VPS: httpbin.org
#
# Usage: ./setup.sh [gateway-url]
#   Default: http://localhost:8080

set -euo pipefail

GW_URL="${1:-http://localhost:8080}"
ADMIN_TOKEN="${STOA_ADMIN_API_TOKEN:?Set STOA_ADMIN_API_TOKEN from Infisical prod/gateway/arena/ADMIN_API_TOKEN}"

echo "==> Checking gateway health..."
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${GW_URL}/health")
if [ "$HTTP_CODE" != "200" ]; then
  echo "FAIL: gateway not healthy (HTTP $HTTP_CODE). Is it running?"
  exit 1
fi
echo "OK: gateway healthy"

echo "==> Registering httpbin proxy route..."
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${GW_URL}/admin/apis" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "arena-httpbin-001",
    "name": "httpbin-arena",
    "tenant_id": "arena",
    "path_prefix": "/httpbin",
    "backend_url": "https://httpbin.org",
    "methods": ["GET", "POST", "PUT", "DELETE"],
    "spec_hash": "arena-static",
    "activated": true
  }')

if [ "$HTTP_CODE" = "201" ]; then
  echo "OK: route created (201)"
elif [ "$HTTP_CODE" = "200" ]; then
  echo "OK: route updated (200)"
else
  echo "FAIL: unexpected response (HTTP $HTTP_CODE)"
  exit 1
fi

echo "==> Verifying proxy route..."
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${GW_URL}/httpbin/get")
if [ "$HTTP_CODE" = "200" ]; then
  echo "OK: proxy to httpbin.org works"
else
  echo "WARN: proxy returned HTTP $HTTP_CODE (may need a moment to propagate)"
fi

echo ""
echo "Done. STOA gateway ready for Arena benchmarks."
echo "  Health: curl ${GW_URL}/health"
echo "  Proxy:  curl ${GW_URL}/httpbin/get"
