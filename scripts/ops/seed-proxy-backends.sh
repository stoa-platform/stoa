#!/usr/bin/env bash
# seed-proxy-backends.sh — Register proxy backends in the gateway.
#
# Registers backend credentials via the gateway admin API and proxy backend
# entries in the CP API for Console visibility.
# Low-risk (CAB-1728): Pushgateway, Healthchecks, n8n, Cloudflare
# High-risk (CAB-1729): Linear, GitHub, Slack Bot, Slack Webhook
#
# Usage:
#   GATEWAY_ADMIN_URL=http://stoa-gateway:80 \
#   CP_API_URL=http://stoa-control-plane-api:80 \
#   bash seed-proxy-backends.sh
#
# Credentials are read from Infisical (via env) or passed directly.
# This script is idempotent — safe to run multiple times (upsert).

set -euo pipefail

GATEWAY_ADMIN_URL="${GATEWAY_ADMIN_URL:-http://stoa-gateway.stoa-system.svc.cluster.local:80}"
CP_API_URL="${CP_API_URL:-http://stoa-control-plane-api.stoa-system.svc.cluster.local:80}"

# Admin API key for the gateway (same as STOA_CONTROL_PLANE_API_KEY)
GW_API_KEY="${STOA_CONTROL_PLANE_API_KEY:-}"
if [[ -z "$GW_API_KEY" ]]; then
  echo "ERROR: STOA_CONTROL_PLANE_API_KEY is required" >&2
  exit 1
fi

register_credential() {
  local route_id="$1" auth_type="$2" header_name="$3" header_value="$4"
  echo "  Registering credential: ${route_id} (${auth_type})"
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    -X POST "${GATEWAY_ADMIN_URL}/admin/backend-credentials" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${GW_API_KEY}" \
    -d "{
      \"route_id\": \"${route_id}\",
      \"auth_type\": \"${auth_type}\",
      \"header_name\": \"${header_name}\",
      \"header_value\": \"${header_value}\"
    }")
  if [[ "$http_code" -lt 300 ]]; then
    echo "    OK (HTTP ${http_code})"
  else
    echo "    WARNING: HTTP ${http_code}"
  fi
}

register_cp_backend() {
  local name="$1" display_name="$2" base_url="$3" auth_type="$4" \
        credential_ref="$5" rate_limit="$6" circuit_breaker="$7" \
        fallback="$8" timeout="$9"
  echo "  Registering CP backend: ${name}"
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    -X POST "${CP_API_URL}/v1/proxy-backends" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${GW_API_KEY}" \
    -d "{
      \"name\": \"${name}\",
      \"display_name\": \"${display_name}\",
      \"base_url\": \"${base_url}\",
      \"auth_type\": \"${auth_type}\",
      \"credential_ref\": \"${credential_ref}\",
      \"rate_limit_rpm\": ${rate_limit},
      \"circuit_breaker_enabled\": ${circuit_breaker},
      \"fallback_direct\": ${fallback},
      \"timeout_secs\": ${timeout}
    }")
  if [[ "$http_code" -lt 300 ]]; then
    echo "    OK (HTTP ${http_code})"
  else
    echo "    WARNING: HTTP ${http_code} (may already exist)"
  fi
}

echo "=== Seeding proxy backends (CAB-1728) ==="
echo ""

# ---------------------------------------------------------------------------
# 1. Pushgateway — no auth (internal K8s service)
# ---------------------------------------------------------------------------
echo "[1/8] Pushgateway"
register_credential "api-proxy:pushgateway" "bearer" "Authorization" "Bearer unused"
register_cp_backend "pushgateway" "Prometheus Pushgateway" \
  "http://pushgateway.monitoring.svc:9091" "api_key" "api-proxy:pushgateway" \
  0 true false 60

# ---------------------------------------------------------------------------
# 2. Healthchecks — no auth (UUID-based URL)
# ---------------------------------------------------------------------------
echo "[2/8] Healthchecks"
register_credential "api-proxy:healthchecks" "bearer" "Authorization" "Bearer unused"
register_cp_backend "healthchecks" "Healthchecks.io" \
  "https://hc.gostoa.dev" "api_key" "api-proxy:healthchecks" \
  100 true false 10

# ---------------------------------------------------------------------------
# 3. n8n — API key in X-N8N-API-KEY header
# ---------------------------------------------------------------------------
echo "[3/8] n8n"
N8N_API_KEY="${N8N_API_KEY:-}"
if [[ -n "$N8N_API_KEY" ]]; then
  register_credential "api-proxy:n8n" "api_key" "X-N8N-API-KEY" "${N8N_API_KEY}"
else
  echo "  SKIP credential (N8N_API_KEY not set — register manually)"
fi
register_cp_backend "n8n" "n8n Workflow Automation" \
  "https://n8n.gostoa.dev" "api_key" "api-proxy:n8n" \
  60 true false 30

# ---------------------------------------------------------------------------
# 4. Cloudflare — Bearer token
# ---------------------------------------------------------------------------
echo "[4/8] Cloudflare"
CF_API_TOKEN="${CF_API_TOKEN:-}"
if [[ -n "$CF_API_TOKEN" ]]; then
  register_credential "api-proxy:cloudflare" "bearer" "Authorization" "Bearer ${CF_API_TOKEN}"
else
  echo "  SKIP credential (CF_API_TOKEN not set — register manually)"
fi
register_cp_backend "cloudflare" "Cloudflare API" \
  "https://api.cloudflare.com/client/v4" "bearer" "api-proxy:cloudflare" \
  200 true false 30

# ---------------------------------------------------------------------------
# 5. Linear — Bearer token (GraphQL API, 1500 req/h)
# ---------------------------------------------------------------------------
echo "[5/8] Linear"
LINEAR_API_KEY="${LINEAR_API_KEY:-}"
if [[ -n "$LINEAR_API_KEY" ]]; then
  register_credential "api-proxy:linear" "bearer" "Authorization" "${LINEAR_API_KEY}"
else
  echo "  SKIP credential (LINEAR_API_KEY not set — register manually)"
fi
register_cp_backend "linear" "Linear Issue Tracker" \
  "https://api.linear.app" "bearer" "api-proxy:linear" \
  1500 true true 30

# ---------------------------------------------------------------------------
# 6. GitHub — Bearer PAT (5000 req/h)
# ---------------------------------------------------------------------------
echo "[6/8] GitHub"
GITHUB_PAT="${GITHUB_PAT:-}"
if [[ -n "$GITHUB_PAT" ]]; then
  register_credential "api-proxy:github" "bearer" "Authorization" "Bearer ${GITHUB_PAT}"
else
  echo "  SKIP credential (GITHUB_PAT not set — register manually)"
fi
register_cp_backend "github" "GitHub API" \
  "https://api.github.com" "bearer" "api-proxy:github" \
  5000 true true 30

# ---------------------------------------------------------------------------
# 7. Slack Bot — Bearer token
# ---------------------------------------------------------------------------
echo "[7/8] Slack Bot"
SLACK_BOT_TOKEN="${SLACK_BOT_TOKEN:-}"
if [[ -n "$SLACK_BOT_TOKEN" ]]; then
  register_credential "api-proxy:slack" "bearer" "Authorization" "Bearer ${SLACK_BOT_TOKEN}"
else
  echo "  SKIP credential (SLACK_BOT_TOKEN not set — register manually)"
fi
register_cp_backend "slack" "Slack Bot API" \
  "https://slack.com/api" "bearer" "api-proxy:slack" \
  60 true true 10

# ---------------------------------------------------------------------------
# 8. Slack Webhook — URL-embedded auth
# ---------------------------------------------------------------------------
echo "[8/8] Slack Webhook"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
if [[ -n "$SLACK_WEBHOOK_URL" ]]; then
  register_credential "api-proxy:slack-webhook" "bearer" "Authorization" "Bearer unused"
  register_cp_backend "slack-webhook" "Slack Incoming Webhook" \
    "${SLACK_WEBHOOK_URL}" "api_key" "api-proxy:slack-webhook" \
    60 true true 5
else
  echo "  SKIP (SLACK_WEBHOOK_URL not set — register manually)"
fi

echo ""
echo "=== Done. Verify: curl ${GATEWAY_ADMIN_URL}/admin/backend-credentials ==="
