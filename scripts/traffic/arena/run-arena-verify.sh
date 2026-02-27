#!/usr/bin/env bash
# Arena Layer 2 — Platform Continuous Verification
#
# Tests 3 Critical User Journeys (CUJs) every 15 minutes:
#   CUJ 1: API Health Chain — API + Gateway + Auth all responding
#   CUJ 2: Auth Flow — OIDC token acquisition + authenticated API call
#   CUJ 3: MCP Discovery→Call — /mcp/capabilities + /mcp/tools/list
#
# Results pushed to Pushgateway as Prometheus metrics.
# Pings Healthchecks dead man's switch on completion.
#
# Env vars:
#   ENDPOINTS          — JSON: {"api":"...","gateway":"...","auth":"..."}
#   PUSHGATEWAY_URL    — Pushgateway URL (default: http://pushgateway.monitoring.svc:9091)
#   PUSHGATEWAY_AUTH   — Basic auth user:pass (optional)
#   HEALTHCHECKS_URL   — Healthchecks ping URL (optional, dead man's switch)
#   OIDC_TOKEN_URL     — Keycloak token endpoint
#   OIDC_CLIENT_ID     — Client ID for healthcheck client
#   OIDC_CLIENT_SECRET — Client secret (from K8s secret)
#   ARENA_INSTANCE     — Instance label (default: "k8s")
#   TIMEOUT            — Request timeout in seconds (default: 5)
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://pushgateway.monitoring.svc:9091}"
ARENA_INSTANCE="${ARENA_INSTANCE:-k8s}"
TIMEOUT="${TIMEOUT:-5}"
WORK_DIR="/tmp/arena-verify"
METRICS_FILE="$WORK_DIR/metrics.txt"

log_json() {
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "{\"time\":\"${ts}\",\"level\":\"INFO\",\"msg\":$1}"
}

log_json "\"Arena L2 platform verification starting\""

if [ -z "${ENDPOINTS:-}" ]; then
  echo "ERROR: ENDPOINTS env var not set" >&2
  exit 1
fi

API_URL=$(echo "$ENDPOINTS" | jq -r '.api')
GATEWAY_URL=$(echo "$ENDPOINTS" | jq -r '.gateway')
AUTH_URL=$(echo "$ENDPOINTS" | jq -r '.auth')

rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
run_cuj() {
  local cuj_name="$1"
  local start_ts end_ts duration_ms http_code status

  start_ts=$(date +%s%N)

  # Execute the CUJ function, capture HTTP code
  if http_code=$("cuj_${cuj_name}" 2>"$WORK_DIR/${cuj_name}_stderr.txt"); then
    status=1
  else
    status=0
    http_code="${http_code:-0}"
  fi

  end_ts=$(date +%s%N)
  duration_ms=$(( (end_ts - start_ts) / 1000000 ))

  # Write result JSON
  cat > "$WORK_DIR/${cuj_name}.json" <<EOF
{"cuj":"${cuj_name}","status":${status},"http_code":"${http_code}","duration_ms":${duration_ms}}
EOF

  if [ "$status" -eq 1 ]; then
    log_json "\"CUJ ${cuj_name}: PASS (${duration_ms}ms)\""
  else
    local stderr_excerpt
    stderr_excerpt=$(head -c 200 "$WORK_DIR/${cuj_name}_stderr.txt" 2>/dev/null | tr '"' "'" || echo "no details")
    log_json "\"CUJ ${cuj_name}: FAIL (${duration_ms}ms, code=${http_code}, err=${stderr_excerpt})\""
  fi
}

# ---------------------------------------------------------------------------
# CUJ 1: API Health Chain
# Checks /health on API, Gateway, and Auth (Keycloak)
# ---------------------------------------------------------------------------
cuj_api_health() {
  local code

  # API health
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "${API_URL}/health" 2>&1)
  [ "$code" -ge 200 ] && [ "$code" -lt 300 ] || { echo "$code"; return 1; }

  # Gateway health
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "${GATEWAY_URL}/health" 2>&1)
  [ "$code" -ge 200 ] && [ "$code" -lt 300 ] || { echo "$code"; return 1; }

  # Auth health (Keycloak realms endpoint)
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "${AUTH_URL}/realms/stoa" 2>&1)
  [ "$code" -ge 200 ] && [ "$code" -lt 300 ] || { echo "$code"; return 1; }

  echo "$code"
}

# ---------------------------------------------------------------------------
# CUJ 2: Auth Flow
# Get OIDC token via client_credentials → call API with Bearer token
# ---------------------------------------------------------------------------
cuj_auth_flow() {
  local token_url="${OIDC_TOKEN_URL:-${AUTH_URL}/realms/stoa/protocol/openid-connect/token}"
  local client_id="${OIDC_CLIENT_ID:-stoa-healthcheck}"
  local client_secret="${OIDC_CLIENT_SECRET:-}"

  if [ -z "$client_secret" ]; then
    echo "no_secret" >&2
    echo "0"
    return 1
  fi

  # Get token
  local token_response
  token_response=$(curl -s --max-time "$TIMEOUT" \
    -d "grant_type=client_credentials" \
    -d "client_id=${client_id}" \
    -d "client_secret=${client_secret}" \
    "$token_url" 2>&1)

  local access_token
  access_token=$(echo "$token_response" | jq -r '.access_token // empty')

  if [ -z "$access_token" ]; then
    echo "token_failed: $(echo "$token_response" | head -c 200)" >&2
    echo "0"
    return 1
  fi

  # Call API with token
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" \
    -H "Authorization: Bearer ${access_token}" \
    "${API_URL}/v1/health" 2>&1)

  [ "$code" -ge 200 ] && [ "$code" -lt 400 ] || { echo "$code"; return 1; }

  echo "$code"
}

# ---------------------------------------------------------------------------
# CUJ 3: MCP Discovery → Tool Call
# GET /mcp/capabilities → POST /mcp/tools/list
# ---------------------------------------------------------------------------
cuj_mcp_discovery() {
  local code body

  # MCP capabilities discovery
  code=$(curl -s -o "$WORK_DIR/mcp_caps.json" -w "%{http_code}" --max-time "$TIMEOUT" \
    "${GATEWAY_URL}/mcp/capabilities" 2>&1)
  [ "$code" -ge 200 ] && [ "$code" -lt 300 ] || { echo "$code"; return 1; }

  # Validate capabilities response has expected fields
  local has_tools
  has_tools=$(jq -r '.capabilities.tools // empty' "$WORK_DIR/mcp_caps.json" 2>/dev/null)
  if [ -z "$has_tools" ]; then
    echo "invalid_capabilities" >&2
    echo "$code"
    return 1
  fi

  # MCP tools list
  code=$(curl -s -o "$WORK_DIR/mcp_tools.json" -w "%{http_code}" --max-time "$TIMEOUT" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
    "${GATEWAY_URL}/mcp/tools/list" 2>&1)
  [ "$code" -ge 200 ] && [ "$code" -lt 300 ] || { echo "$code"; return 1; }

  echo "$code"
}

# ---------------------------------------------------------------------------
# Run all CUJs
# ---------------------------------------------------------------------------
CUJ_NAMES="api_health auth_flow mcp_discovery"
TOTAL=0
PASSED=0

for cuj in $CUJ_NAMES; do
  run_cuj "$cuj"
  TOTAL=$((TOTAL + 1))
  status=$(jq -r '.status' "$WORK_DIR/${cuj}.json")
  [ "$status" -eq 1 ] && PASSED=$((PASSED + 1))
done

log_json "\"Platform verification: ${PASSED}/${TOTAL} CUJs passed\""

# ---------------------------------------------------------------------------
# Generate Prometheus metrics
# ---------------------------------------------------------------------------
cat > "$METRICS_FILE" <<EOF
# HELP platform_verify_cuj_status CUJ pass (1) or fail (0)
# TYPE platform_verify_cuj_status gauge
EOF

for cuj in $CUJ_NAMES; do
  status=$(jq -r '.status' "$WORK_DIR/${cuj}.json")
  echo "platform_verify_cuj_status{cuj=\"${cuj}\"} ${status}" >> "$METRICS_FILE"
done

cat >> "$METRICS_FILE" <<EOF
# HELP platform_verify_cuj_duration_seconds CUJ execution duration
# TYPE platform_verify_cuj_duration_seconds gauge
EOF

for cuj in $CUJ_NAMES; do
  duration_ms=$(jq -r '.duration_ms' "$WORK_DIR/${cuj}.json")
  duration_s=$(echo "scale=3; ${duration_ms}/1000" | bc 2>/dev/null || echo "0")
  echo "platform_verify_cuj_duration_seconds{cuj=\"${cuj}\"} ${duration_s}" >> "$METRICS_FILE"
done

cat >> "$METRICS_FILE" <<EOF
# HELP platform_verify_overall_score CUJs passed out of total
# TYPE platform_verify_overall_score gauge
platform_verify_overall_score ${PASSED}
# HELP platform_verify_total Total number of CUJs
# TYPE platform_verify_total gauge
platform_verify_total ${TOTAL}
# HELP platform_verify_last_run_timestamp Unix timestamp of last verification run
# TYPE platform_verify_last_run_timestamp gauge
platform_verify_last_run_timestamp $(date +%s)
EOF

# ---------------------------------------------------------------------------
# Push to Pushgateway
# ---------------------------------------------------------------------------
PUSH_URL="${PUSHGATEWAY_URL}/metrics/job/platform_verify/instance/${ARENA_INSTANCE}"
CURL_AUTH=""
if [ -n "${PUSHGATEWAY_AUTH:-}" ]; then
  CURL_AUTH="-u ${PUSHGATEWAY_AUTH}"
fi

HTTP_CODE=$(curl -s -o "$WORK_DIR/push_response.txt" -w "%{http_code}" -X PUT \
  --data-binary @"$METRICS_FILE" \
  -H "Content-Type: text/plain" $CURL_AUTH "$PUSH_URL" 2>/dev/null)
[ -z "$HTTP_CODE" ] && HTTP_CODE="000"

if [ "$HTTP_CODE" -lt 300 ] && [ "$HTTP_CODE" != "000" ]; then
  METRIC_LINES=$(wc -l < "$METRICS_FILE" | tr -d ' ')
  log_json "\"Pushed ${METRIC_LINES} metric lines to Pushgateway (HTTP ${HTTP_CODE})\""
else
  RESP_BODY=$(head -c 500 "$WORK_DIR/push_response.txt" 2>/dev/null | tr '"' "'" || echo "")
  log_json "\"WARNING: Pushgateway returned HTTP ${HTTP_CODE}: ${RESP_BODY}\""
fi

# ---------------------------------------------------------------------------
# Ping Healthchecks (dead man's switch)
# ---------------------------------------------------------------------------
if [ -n "${HEALTHCHECKS_URL:-}" ]; then
  if [ "$PASSED" -eq "$TOTAL" ]; then
    curl -s -o /dev/null --max-time 5 "${HEALTHCHECKS_URL}" 2>/dev/null || true
    log_json "\"Healthchecks pinged (all CUJs passed)\""
  else
    curl -s -o /dev/null --max-time 5 "${HEALTHCHECKS_URL}/fail" 2>/dev/null || true
    log_json "\"Healthchecks pinged /fail (${PASSED}/${TOTAL} CUJs passed)\""
  fi
fi

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
rm -rf "$WORK_DIR"
log_json "\"Arena L2 platform verification finished (${PASSED}/${TOTAL})\""
