#!/usr/bin/env bash
# stoa-proxy.sh — Reusable library for calling APIs through STOA Gateway proxy.
#
# Sources this file to get:
#   stoa_proxy_call METHOD BACKEND PATH [CURL_EXTRA_ARGS...]
#   stoa_proxy_push_metrics BACKEND JOB_PATH METRICS_FILE
#   stoa_proxy_ping_healthcheck BACKEND UUID [/fail]
#
# Required env vars:
#   STOA_PROXY_URL        — Gateway URL (e.g., https://mcp.gostoa.dev or http://stoa-gateway.stoa-system.svc:80)
#   STOA_PROXY_CLIENT_ID  — Keycloak client ID for service account
#   STOA_PROXY_CLIENT_SEC — Keycloak client secret
#   STOA_KEYCLOAK_URL     — Keycloak base URL (e.g., https://auth.gostoa.dev)
#   STOA_KEYCLOAK_REALM   — Keycloak realm (default: stoa)
#
# Optional:
#   STOA_PROXY_FALLBACK   — "true" to fall back to direct call on proxy failure
#   STOA_PROXY_TOKEN      — Pre-fetched token (skip OAuth2 flow)

# Token cache (in-memory for the script lifetime)
_STOA_TOKEN=""
_STOA_TOKEN_EXPIRES=0

# Get an OAuth2 token via client_credentials grant.
# Caches the token until 30s before expiry.
stoa_proxy_get_token() {
  local now
  now=$(date +%s)
  # Return cached token if still valid (30s margin)
  if [[ -n "$_STOA_TOKEN" && "$now" -lt "$((_STOA_TOKEN_EXPIRES - 30))" ]]; then
    echo "$_STOA_TOKEN"
    return 0
  fi

  # Pre-set token (CI environments)
  if [[ -n "${STOA_PROXY_TOKEN:-}" ]]; then
    _STOA_TOKEN="$STOA_PROXY_TOKEN"
    _STOA_TOKEN_EXPIRES=$((now + 3600))
    echo "$_STOA_TOKEN"
    return 0
  fi

  local realm="${STOA_KEYCLOAK_REALM:-stoa}"
  local token_url="${STOA_KEYCLOAK_URL}/realms/${realm}/protocol/openid-connect/token"

  local response
  response=$(curl -sf --max-time 10 \
    -d "grant_type=client_credentials" \
    -d "client_id=${STOA_PROXY_CLIENT_ID}" \
    -d "client_secret=${STOA_PROXY_CLIENT_SEC}" \
    "$token_url" 2>/dev/null) || {
    echo "ERROR: Failed to get OAuth2 token from ${token_url}" >&2
    return 1
  }

  _STOA_TOKEN=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null) || {
    echo "ERROR: Failed to parse token response" >&2
    return 1
  }
  local expires_in
  expires_in=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('expires_in', 300))" 2>/dev/null)
  _STOA_TOKEN_EXPIRES=$((now + expires_in))

  echo "$_STOA_TOKEN"
}

# Call an API through the STOA Gateway proxy.
# Usage: stoa_proxy_call METHOD BACKEND PATH [CURL_EXTRA_ARGS...]
# Example: stoa_proxy_call GET linear /graphql -d '{"query": "..."}'
stoa_proxy_call() {
  local method="$1" backend="$2" path="$3"
  shift 3

  local token
  token=$(stoa_proxy_get_token) || {
    if [[ "${STOA_PROXY_FALLBACK:-}" == "true" ]]; then
      echo "WARNING: Token fetch failed, cannot proxy. Caller should fall back." >&2
      return 2
    fi
    return 1
  }

  local url="${STOA_PROXY_URL}/apis/${backend}${path}"
  curl -sf --max-time 30 \
    -X "$method" \
    -H "Authorization: Bearer ${token}" \
    "$@" \
    "$url"
}

# Push Prometheus metrics through the gateway proxy.
# Usage: stoa_proxy_push_metrics JOB_PATH METRICS_FILE [RESPONSE_FILE]
# Falls back to direct PUSHGATEWAY_URL if proxy fails and STOA_PROXY_FALLBACK=true.
stoa_proxy_push_metrics() {
  local job_path="$1" metrics_file="$2" response_file="${3:-/dev/null}"

  local token http_code
  token=$(stoa_proxy_get_token 2>/dev/null) || token=""

  if [[ -n "$token" && -n "${STOA_PROXY_URL:-}" ]]; then
    local url="${STOA_PROXY_URL}/apis/pushgateway/metrics/job/${job_path}"
    http_code=$(curl -s -o "$response_file" -w "%{http_code}" --max-time 10 \
      -X PUT --data-binary @"$metrics_file" \
      -H "Content-Type: text/plain" \
      -H "Authorization: Bearer ${token}" \
      "$url" 2>/dev/null)
    [[ -z "$http_code" ]] && http_code="000"

    if [[ "$http_code" -lt 300 && "$http_code" != "000" ]]; then
      return 0
    fi
    echo "WARNING: Gateway proxy returned HTTP ${http_code} for pushgateway push" >&2
  fi

  # Fallback to direct pushgateway
  if [[ -n "${PUSHGATEWAY_URL:-}" ]]; then
    local push_url="${PUSHGATEWAY_URL}/metrics/job/${job_path}"
    local curl_auth=""
    [[ -n "${PUSHGATEWAY_AUTH:-}" ]] && curl_auth="-u ${PUSHGATEWAY_AUTH}"
    http_code=$(curl -s -o "$response_file" -w "%{http_code}" --max-time 10 \
      -X PUT --data-binary @"$metrics_file" \
      -H "Content-Type: text/plain" $curl_auth "$push_url" 2>/dev/null)
    [[ -z "$http_code" ]] && http_code="000"
    if [[ "$http_code" -lt 300 && "$http_code" != "000" ]]; then
      return 0
    fi
    echo "WARNING: Direct pushgateway returned HTTP ${http_code}" >&2
  fi

  return 1
}

# Ping Healthchecks through the gateway proxy.
# Usage: stoa_proxy_ping_healthcheck UUID [/fail]
# Falls back to direct HEALTHCHECKS_URL if proxy fails.
stoa_proxy_ping_healthcheck() {
  local uuid="$1" suffix="${2:-}"

  local token
  token=$(stoa_proxy_get_token 2>/dev/null) || token=""

  if [[ -n "$token" && -n "${STOA_PROXY_URL:-}" ]]; then
    local url="${STOA_PROXY_URL}/apis/healthchecks/ping/${uuid}${suffix}"
    if curl -sf -o /dev/null --max-time 5 \
      -H "Authorization: Bearer ${token}" \
      "$url" 2>/dev/null; then
      return 0
    fi
    echo "WARNING: Gateway proxy failed for healthchecks ping" >&2
  fi

  # Fallback to direct healthchecks URL
  if [[ -n "${HEALTHCHECKS_URL:-}" ]]; then
    curl -s -o /dev/null --max-time 5 "${HEALTHCHECKS_URL}${suffix}" 2>/dev/null || true
    return 0
  fi

  return 1
}

# Post a Linear GraphQL mutation through the gateway proxy.
# Usage: stoa_proxy_linear_graphql QUERY [RESPONSE_FILE]
# Falls back to direct LINEAR_API_KEY if proxy fails.
stoa_proxy_linear_graphql() {
  local query="$1" response_file="${2:-/dev/null}"

  local token http_code
  token=$(stoa_proxy_get_token 2>/dev/null) || token=""

  if [[ -n "$token" && -n "${STOA_PROXY_URL:-}" ]]; then
    http_code=$(curl -s -o "$response_file" -w "%{http_code}" --max-time 15 \
      -X POST "${STOA_PROXY_URL}/apis/linear/graphql" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${token}" \
      -d "$query" 2>/dev/null)
    [[ -z "$http_code" ]] && http_code="000"
    if [[ "$http_code" -lt 300 && "$http_code" != "000" ]]; then
      return 0
    fi
    echo "WARNING: Gateway proxy returned HTTP ${http_code} for Linear" >&2
  fi

  # Fallback to direct Linear API
  if [[ -n "${LINEAR_API_KEY:-}" ]]; then
    http_code=$(curl -s -o "$response_file" -w "%{http_code}" --max-time 15 \
      -X POST "https://api.linear.app/graphql" \
      -H "Content-Type: application/json" \
      -H "Authorization: ${LINEAR_API_KEY}" \
      -d "$query" 2>/dev/null)
    [[ -z "$http_code" ]] && http_code="000"
    if [[ "$http_code" -lt 300 && "$http_code" != "000" ]]; then
      return 0
    fi
  fi

  return 1
}

# Send a Slack message through the gateway proxy (Bot API).
# Usage: stoa_proxy_slack_post PAYLOAD [RESPONSE_FILE]
# Falls back to direct SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL.
stoa_proxy_slack_post() {
  local payload="$1" response_file="${2:-/dev/null}"

  local token http_code
  token=$(stoa_proxy_get_token 2>/dev/null) || token=""

  # Try gateway proxy -> Slack Bot API
  if [[ -n "$token" && -n "${STOA_PROXY_URL:-}" ]]; then
    http_code=$(curl -s -o "$response_file" -w "%{http_code}" --max-time 10 \
      -X POST "${STOA_PROXY_URL}/apis/slack/chat.postMessage" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${token}" \
      -d "$payload" 2>/dev/null)
    [[ -z "$http_code" ]] && http_code="000"
    if [[ "$http_code" -lt 300 && "$http_code" != "000" ]]; then
      return 0
    fi
    echo "WARNING: Gateway proxy returned HTTP ${http_code} for Slack" >&2
  fi

  # Fallback 1: direct Bot API
  if [[ -n "${SLACK_BOT_TOKEN:-}" && -n "${SLACK_CHANNEL_ID:-}" ]]; then
    http_code=$(curl -s -o "$response_file" -w "%{http_code}" --max-time 10 \
      -X POST "https://slack.com/api/chat.postMessage" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${SLACK_BOT_TOKEN}" \
      -d "$payload" 2>/dev/null)
    [[ -z "$http_code" ]] && http_code="000"
    if [[ "$http_code" -lt 300 && "$http_code" != "000" ]]; then
      return 0
    fi
  fi

  # Fallback 2: direct webhook
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    curl -s -o "$response_file" --max-time 10 \
      -X POST -H "Content-Type: application/json" \
      -d "$payload" "$SLACK_WEBHOOK_URL" 2>/dev/null || true
    return 0
  fi

  return 1
}
