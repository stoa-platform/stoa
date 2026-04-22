#!/usr/bin/env bash
# =============================================================================
# CAB-2150 (parent CAB-2148): Demo reset harness.
# =============================================================================
# Calls the cp-api demo reset endpoint (CAB-2149 contract) to return the
# platform to a known demo-ready state. Idempotent by contract: server
# guarantees safe replay. Exits 0 ONLY if reset fully completed.
#
# Contract assumption (CAB-2149, not yet merged):
#   POST ${STOA_API_URL}/api/v1/demo/reset
#     Authorization: Bearer ${STOA_API_TOKEN}
#   -> 200 {"status": "reset_complete", "tenants": N, "duration_ms": M}
#   -> any other status = non-zero exit + stderr diagnostic
#
# Usage: ./reset-demo.sh [--timeout SECONDS]
# Env:
#   STOA_API_URL     (required) Control Plane API base URL
#   STOA_API_TOKEN   (required) Bearer token with demo-admin scope
# =============================================================================

set -euo pipefail

TIMEOUT=60
while [ $# -gt 0 ]; do
    case "$1" in
        --timeout) TIMEOUT="${2:?--timeout needs a value}"; shift 2 ;;
        -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

: "${STOA_API_URL:?STOA_API_URL must be set (e.g. https://api.gostoa.dev)}"
: "${STOA_API_TOKEN:?STOA_API_TOKEN must be set (bearer token, demo-admin scope)}"

log() { printf '[reset-demo] %s\n' "$*"; }
fail() { printf '[reset-demo] FAIL: %s\n' "$*" >&2; exit 1; }

log "POST ${STOA_API_URL}/api/v1/demo/reset (timeout=${TIMEOUT}s)"

TMP_BODY="$(mktemp)"
trap 'rm -f "$TMP_BODY"' EXIT

HTTP_CODE="$(
    curl -sS --max-time "$TIMEOUT" \
        -o "$TMP_BODY" \
        -w '%{http_code}' \
        -X POST \
        -H "Authorization: Bearer ${STOA_API_TOKEN}" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json' \
        "${STOA_API_URL%/}/api/v1/demo/reset" \
    || true
)"

if [ -z "$HTTP_CODE" ]; then
    fail "curl produced no HTTP status (network or DNS failure)"
fi

if [ "$HTTP_CODE" != "200" ]; then
    log "response body:"
    cat "$TMP_BODY" >&2 || true
    fail "unexpected HTTP ${HTTP_CODE}"
fi

STATUS="$(grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' "$TMP_BODY" \
    | head -n1 | sed 's/.*"\([^"]*\)"$/\1/' || true)"

if [ "$STATUS" != "reset_complete" ]; then
    log "response body:"
    cat "$TMP_BODY" >&2 || true
    fail "server returned status='${STATUS:-<missing>}', expected 'reset_complete'"
fi

log "reset complete ($(cat "$TMP_BODY"))"
exit 0
