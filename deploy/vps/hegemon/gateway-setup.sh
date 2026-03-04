#!/usr/bin/env bash
# Setup STOA Gateway routes and credentials for HEGEMON workers.
# Run AFTER docker-compose.gateway.yml is up.
#
# What this script does:
#   1. Wait for both gateways to be healthy
#   2. Register Anthropic API route on external gateway (credential injection)
#   3. Verify credential injection works (request without API key → gateway injects → upstream responds)
#
# Usage: ./gateway-setup.sh
# Env vars (from ~/.env.hegemon):
#   ANTHROPIC_API_KEY  — Real Anthropic API key (injected by external gateway)
set -euo pipefail

source "${HOME}/.env.hegemon" 2>/dev/null || true

INTERNAL_URL="${GATEWAY_INTERNAL_URL:-http://localhost:8090}"
EXTERNAL_URL="${GATEWAY_EXTERNAL_URL:-http://localhost:8091}"
LOG_TAG="[gateway-setup]"

log() { echo "${LOG_TAG} $(date '+%H:%M:%S') $*"; }

# ─── 1. Wait for gateways ─────────────────────────────────────────────────
log "Waiting for gateways to be healthy..."

wait_for_health() {
  local url="$1"
  local name="$2"
  local max_attempts=30

  for i in $(seq 1 $max_attempts); do
    if curl -sf "${url}/health" > /dev/null 2>&1; then
      log "${name} healthy"
      return 0
    fi
    sleep 2
  done

  log "ERROR: ${name} not healthy after ${max_attempts} attempts"
  return 1
}

wait_for_health "$INTERNAL_URL" "Internal Gateway (8090)"
wait_for_health "$EXTERNAL_URL" "External Gateway (8091)"

# ─── 2. Register routes on external gateway ────────────────────────────────
# The external gateway in proxy mode uses the LLM proxy passthrough.
# Routes are configured via env vars in docker-compose.gateway.yml:
#   STOA_LLM_PROXY_UPSTREAM_URL = https://api.anthropic.com
#   STOA_LLM_PROXY_UPSTREAM_API_KEY = <real key>
#
# Workers send requests to http://localhost:8091/v1/messages (Anthropic API path)
# Gateway proxies to upstream, injecting the real API key.

log "External gateway route: /v1/* → api.anthropic.com (credential injection via LLM proxy)"

# ─── 3. Verify credential injection ───────────────────────────────────────
log "Verifying credential injection..."

# Test: send a minimal request to the external gateway without an API key.
# The gateway should inject the real key and proxy to Anthropic.
VERIFY_RESPONSE=$(curl -sf -o /dev/null -w "%{http_code}" \
  -X POST "${EXTERNAL_URL}/v1/messages" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "hi"}]
  }' 2>/dev/null || echo "000")

if [ "$VERIFY_RESPONSE" = "200" ]; then
  log "Credential injection: OK (200)"
elif [ "$VERIFY_RESPONSE" = "429" ]; then
  log "Credential injection: OK (429 rate limited — key was injected)"
elif [ "$VERIFY_RESPONSE" = "401" ]; then
  log "WARNING: Credential injection may not be working (401 Unauthorized)"
  log "  Check ANTHROPIC_API_KEY is set in docker-compose.gateway.yml"
elif [ "$VERIFY_RESPONSE" = "000" ]; then
  log "WARNING: External gateway unreachable for verification"
else
  log "Credential injection: response ${VERIFY_RESPONSE} (may be OK — key was forwarded)"
fi

# ─── 4. Summary ───────────────────────────────────────────────────────────
log ""
log "=== Gateway Setup Complete ==="
log "  Internal Gateway: ${INTERNAL_URL} (edge-mcp, JWT auth, supervision)"
log "  External Gateway: ${EXTERNAL_URL} (proxy, credential injection, circuit breaker)"
log ""
log "Workers should set:"
log "  ANTHROPIC_BASE_URL=${EXTERNAL_URL}"
log "  (no ANTHROPIC_API_KEY needed — gateway injects it)"
