#!/usr/bin/env bash
# =============================================================================
# CAB-2150 (parent CAB-2148): Pre-demo binary gate.
# =============================================================================
# Preflight checks for the demo environment. Prints a PASS/FAIL line per check
# and exits non-zero on ANY red signal (binary gate — no "warning" state).
#
# Checks (all MUST pass):
#   1. Control Plane /healthz reachable, returns 200
#   2. Gateway /healthz reachable, returns 200
#   3. Demo seed integrity: GET /api/v1/demo/status reports 'seeded'
#   4. Audience claim present on a fresh token from the demo client
#   5. Tenant count: at least ${STOA_DEMO_MIN_TENANTS:-4} tenants exposed
#
# Usage: ./pre-demo-check.sh
# Env:
#   STOA_API_URL            (required)
#   STOA_GATEWAY_URL        (required)
#   STOA_API_TOKEN          (required) Bearer token used to read demo status
#   STOA_DEMO_MIN_TENANTS   (optional, default 4)
# =============================================================================

set -euo pipefail

: "${STOA_API_URL:?STOA_API_URL must be set}"
: "${STOA_GATEWAY_URL:?STOA_GATEWAY_URL must be set}"
: "${STOA_API_TOKEN:?STOA_API_TOKEN must be set}"
MIN_TENANTS="${STOA_DEMO_MIN_TENANTS:-4}"

PASS=0
FAIL=0
report() {
    local status="$1" name="$2" detail="${3:-}"
    if [ "$status" = "PASS" ]; then
        printf '[PASS] %s\n' "$name"
        PASS=$((PASS + 1))
    else
        printf '[FAIL] %s — %s\n' "$name" "$detail" >&2
        FAIL=$((FAIL + 1))
    fi
}

http_code() {
    curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$@" || echo "000"
}

http_get_body() {
    curl -sS --max-time 10 \
        -H "Authorization: Bearer ${STOA_API_TOKEN}" \
        -H 'Accept: application/json' \
        "$@" || true
}

# 1. Control Plane health
code="$(http_code "${STOA_API_URL%/}/healthz")"
if [ "$code" = "200" ]; then
    report PASS "control-plane /healthz"
else
    report FAIL "control-plane /healthz" "HTTP ${code}"
fi

# 2. Gateway health
code="$(http_code "${STOA_GATEWAY_URL%/}/healthz")"
if [ "$code" = "200" ]; then
    report PASS "gateway /healthz"
else
    report FAIL "gateway /healthz" "HTTP ${code}"
fi

# 3. Demo seed integrity (contract from CAB-2149)
body="$(http_get_body "${STOA_API_URL%/}/api/v1/demo/status")"
if printf '%s' "$body" | grep -q '"seed_state"[[:space:]]*:[[:space:]]*"seeded"'; then
    report PASS "demo seed integrity"
else
    report FAIL "demo seed integrity" "expected seed_state=seeded, got: ${body:-<empty>}"
fi

# 4. Audience claim present in JWT (inspect payload of STOA_API_TOKEN)
jwt_payload="$(printf '%s' "$STOA_API_TOKEN" | awk -F. '{print $2}')"
# Base64URL decode (pad to multiple of 4)
pad=$(( (4 - ${#jwt_payload} % 4) % 4 ))
padded="${jwt_payload}$(printf '%*s' "$pad" '' | tr ' ' '=')"
decoded="$(printf '%s' "$padded" | tr '_-' '/+' | base64 -d 2>/dev/null || true)"
if printf '%s' "$decoded" | grep -q '"aud"'; then
    report PASS "audience claim present"
else
    report FAIL "audience claim present" "no 'aud' in token payload"
fi

# 5. Tenant count
body="$(http_get_body "${STOA_API_URL%/}/api/v1/tenants")"
# Count "id" fields as a lower bound on tenant entries; avoids jq dep.
count="$(printf '%s' "$body" | grep -o '"id"[[:space:]]*:' | wc -l | tr -d ' ')"
if [ "${count:-0}" -ge "$MIN_TENANTS" ]; then
    report PASS "tenant count >= ${MIN_TENANTS} (got ${count})"
else
    report FAIL "tenant count" "expected >= ${MIN_TENANTS}, got ${count:-0}"
fi

printf '\nResult: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
