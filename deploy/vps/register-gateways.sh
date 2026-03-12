#!/usr/bin/env bash
# Register all VPS third-party gateways with the STOA Control Plane (CAB-1781).
#
# These gateways (Kong, Gravitee, webMethods) cannot self-register — they must
# be registered via the admin API so the Console can manage them through adapters.
#
# Prerequisites:
#   - STOA_API_TOKEN: Bearer token from Keycloak (cpi-admin role)
#   - Gateways must be reachable from the CP API for health checks
#
# Usage:
#   export STOA_API_TOKEN="<bearer-token>"
#   ./register-gateways.sh [api-url]
#
# Rollback: Delete gateways from Console UI or via:
#   curl -X DELETE ${API_URL}/v1/admin/gateways/<id> -H "Authorization: Bearer ${STOA_API_TOKEN}"

set -euo pipefail

API_URL="${1:-https://api.gostoa.dev}"
TOKEN="${STOA_API_TOKEN:?Set STOA_API_TOKEN (Keycloak Bearer token with cpi-admin role)}"

register_gateway() {
  local name="$1"
  local display_name="$2"
  local gateway_type="$3"
  local environment="$4"
  local base_url="$5"
  local capabilities="$6"

  echo "==> Registering ${display_name} (${gateway_type})..."

  HTTP_CODE=$(curl -s -o /tmp/gw-register-response.json -w '%{http_code}' \
    -X POST "${API_URL}/v1/admin/gateways" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"${name}\",
      \"display_name\": \"${display_name}\",
      \"gateway_type\": \"${gateway_type}\",
      \"environment\": \"${environment}\",
      \"base_url\": \"${base_url}\",
      \"capabilities\": [${capabilities}],
      \"tags\": [\"vps\", \"arena\", \"auto-registered\"]
    }")

  case "$HTTP_CODE" in
    201) echo "  OK: registered (201)" ;;
    200) echo "  OK: updated (200)" ;;
    409) echo "  SKIP: already exists (409)" ;;
    *)
      echo "  FAIL: HTTP ${HTTP_CODE}"
      cat /tmp/gw-register-response.json 2>/dev/null || true
      echo ""
      ;;
  esac
}

echo "Registering third-party VPS gateways with ${API_URL}"
echo "---"

# Kong VPS — DB-less, declarative config
# Admin API on port 8001, proxy on 8000
# Firewall: CP API must reach 54.36.209.237:8001
register_gateway \
  "kong-vps" \
  "Kong Gateway (VPS Arena)" \
  "kong" \
  "production" \
  "http://54.36.209.237:8001" \
  '"rest", "rate_limiting"'

# Gravitee VPS — APIM v4, management API
# Management API on port 8083, gateway on 8082
# Firewall: CP API must reach 54.36.209.237:8083
register_gateway \
  "gravitee-vps" \
  "Gravitee APIM (VPS Arena)" \
  "gravitee" \
  "production" \
  "http://54.36.209.237:8083" \
  '"rest", "rate_limiting"'

# webMethods VPS — Software AG trial
# Admin REST on port 5555, UI on 9072
# Firewall: CP API must reach 51.255.201.17:5555
register_gateway \
  "webmethods-vps" \
  "webMethods API Gateway (VPS)" \
  "webmethods" \
  "production" \
  "http://51.255.201.17:5555" \
  '"rest", "oidc", "rate_limiting"'

echo ""
echo "---"
echo "Done. Verify in Console: https://console.gostoa.dev/gateways"
echo ""
echo "Firewall requirements (CP API → VPS admin ports):"
echo "  Kong:       54.36.209.237:8001"
echo "  Gravitee:   54.36.209.237:8083"
echo "  webMethods: 51.255.201.17:5555"
