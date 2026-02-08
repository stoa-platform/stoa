#!/bin/bash
# =============================================================================
# CAB-1043: STOA Platform Smoke Test Gate (Level 1 — curl-based)
# =============================================================================
# Usage:
#   bash scripts/smoke-test.sh                              # default (gostoa.dev)
#   BASE_DOMAIN=localhost:8080 bash scripts/smoke-test.sh   # local docker-compose
#   npm run test:smoke                                      # via npm script
#
# Environment variables:
#   BASE_DOMAIN          — base domain (default: gostoa.dev)
#   KEYCLOAK_REALM       — Keycloak realm (default: stoa)
#   KEYCLOAK_CLIENT      — OIDC client_id (default: stoa-portal)
#   ALEX_USER / ALEX_PASSWORD
#   PARZIVAL_USER / PARZIVAL_PASSWORD
#   SORRENTO_USER / SORRENTO_PASSWORD
#   MIN_CATALOGUE_APIS   — minimum APIs in catalogue (default: 12)
#
# Exit codes:
#   0 — GATE PASSED (all checks pass)
#   1 — GATE FAILED (one or more checks failed)
# =============================================================================

set -uo pipefail

# =============================================================================
# Configuration
# =============================================================================

BASE_DOMAIN="${BASE_DOMAIN:-gostoa.dev}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-stoa}"
KEYCLOAK_CLIENT="${KEYCLOAK_CLIENT:-stoa-portal}"
MIN_CATALOGUE_APIS="${MIN_CATALOGUE_APIS:-12}"

# Detect protocol: if the domain contains localhost or a port, use http
if [[ "$BASE_DOMAIN" == *"localhost"* || "$BASE_DOMAIN" == *":"* ]]; then
    PROTO="http"
else
    PROTO="https"
fi

PORTAL_URL="${PROTO}://portal.${BASE_DOMAIN}"
AUTH_URL="${PROTO}://auth.${BASE_DOMAIN}"
MCP_URL="${PROTO}://mcp.${BASE_DOMAIN}"
API_URL="${PROTO}://api.${BASE_DOMAIN}"

# Persona credentials (from env vars, with safe defaults for CI)
ALEX_USER="${ALEX_USER:-}"
ALEX_PASSWORD="${ALEX_PASSWORD:-}"
PARZIVAL_USER="${PARZIVAL_USER:-}"
PARZIVAL_PASSWORD="${PARZIVAL_PASSWORD:-}"
SORRENTO_USER="${SORRENTO_USER:-}"
SORRENTO_PASSWORD="${SORRENTO_PASSWORD:-}"

# =============================================================================
# State
# =============================================================================

TOTAL=8
PASSED=0
FAILED=0
BLOCKING_FAILED=0

# Track results for summary
declare -a RESULTS=()

# =============================================================================
# Helpers
# =============================================================================

# Millisecond timer using perl (portable across macOS and Linux)
now_ms() {
    perl -MTime::HiRes=gettimeofday -e 'my ($s, $us) = gettimeofday(); printf "%d\n", $s * 1000 + int($us / 1000)'
}

# Format audit line with dots padding
# Usage: audit_line "AUDIT-N" "Description" "PASS|FAIL" "detail" elapsed_ms is_blocking
audit_line() {
    local id="$1"
    local desc="$2"
    local status="$3"
    local detail="$4"
    local elapsed="$5"
    local blocking="${6:-false}"

    local label="${id}  ${desc}"
    local max_len=42
    local current_len=${#label}
    local dots_count=$((max_len - current_len))
    if [[ $dots_count -lt 3 ]]; then
        dots_count=3
    fi
    local dots
    dots=$(printf '.%.0s' $(seq 1 "$dots_count"))

    if [[ "$status" == "PASS" ]]; then
        local line="${label} ${dots} PASS (${elapsed}ms)"
        RESULTS+=("$line")
        ((PASSED++))
    else
        local line="${label} ${dots} FAIL (${detail})"
        RESULTS+=("$line")
        ((FAILED++))
        if [[ "$blocking" == "true" ]]; then
            ((BLOCKING_FAILED++))
        fi
    fi
}

# Curl wrapper that returns HTTP status code
# Usage: http_code=$(curl_status URL)
curl_status() {
    curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$1" 2>/dev/null || echo "000"
}

# Curl wrapper that returns body
# Usage: body=$(curl_body URL)
curl_body() {
    curl -s --max-time 10 "$1" 2>/dev/null || echo ""
}

# Get Keycloak token via password grant
# Usage: token=$(get_token username password)
get_token() {
    local user="$1"
    local pass="$2"
    local token_url="${AUTH_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token"

    local response
    response=$(curl -s --max-time 10 -X POST "$token_url" \
        -d "grant_type=password" \
        -d "client_id=${KEYCLOAK_CLIENT}" \
        -d "username=${user}" \
        -d "password=${pass}" 2>/dev/null)

    echo "$response" | jq -r '.access_token // empty' 2>/dev/null
}

# =============================================================================
# Prerequisite check
# =============================================================================

check_prereqs() {
    local missing=0
    for cmd in curl jq openssl dig; do
        if ! command -v "$cmd" &>/dev/null; then
            echo "ERROR: required command not found: $cmd"
            ((missing++))
        fi
    done
    if [[ $missing -gt 0 ]]; then
        echo "Install missing dependencies and retry."
        exit 1
    fi
}

# =============================================================================
# AUDIT CHECKS
# =============================================================================

# AUDIT-1: Portal HTTP 200 (BLOCKING)
audit_1() {
    local start
    start=$(now_ms)
    local code
    code=$(curl_status "$PORTAL_URL")
    local elapsed=$(( $(now_ms) - start ))

    if [[ "$code" == "200" ]]; then
        audit_line "AUDIT-1" "Portal HTTP 200" "PASS" "" "$elapsed" "true"
    else
        audit_line "AUDIT-1" "Portal HTTP 200" "FAIL" "HTTP ${code}" "$elapsed" "true"
    fi
}

# AUDIT-2: Keycloak OIDC discovery (BLOCKING)
audit_2() {
    local start
    start=$(now_ms)
    local oidc_url="${AUTH_URL}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"
    local code
    code=$(curl_status "$oidc_url")
    local elapsed=$(( $(now_ms) - start ))

    if [[ "$code" == "200" ]]; then
        audit_line "AUDIT-2" "Keycloak OIDC" "PASS" "" "$elapsed" "true"
    else
        audit_line "AUDIT-2" "Keycloak OIDC" "FAIL" "HTTP ${code}" "$elapsed" "true"
    fi
}

# AUDIT-3: MCP Gateway health
audit_3() {
    local start
    start=$(now_ms)

    # Try /health first, fall back to /sse
    local code
    code=$(curl_status "${MCP_URL}/health")
    if [[ "$code" != "200" ]]; then
        code=$(curl_status "${MCP_URL}/sse")
    fi
    local elapsed=$(( $(now_ms) - start ))

    if [[ "$code" == "200" ]]; then
        audit_line "AUDIT-3" "MCP Gateway" "PASS" "" "$elapsed" "false"
    else
        audit_line "AUDIT-3" "MCP Gateway" "FAIL" "HTTP ${code}" "$elapsed" "false"
    fi
}

# AUDIT-4: Control Plane API health
audit_4() {
    local start
    start=$(now_ms)
    local code
    code=$(curl_status "${API_URL}/health")
    local elapsed=$(( $(now_ms) - start ))

    if [[ "$code" == "200" ]]; then
        audit_line "AUDIT-4" "Control Plane API" "PASS" "" "$elapsed" "false"
    else
        audit_line "AUDIT-4" "Control Plane API" "FAIL" "HTTP ${code}" "$elapsed" "false"
    fi
}

# AUDIT-5: Catalogue >= N APIs
audit_5() {
    local start
    start=$(now_ms)

    local body
    body=$(curl_body "${API_URL}/v1/portal/apis")
    local count
    count=$(echo "$body" | jq '.apis | length // 0' 2>/dev/null || echo "0")
    local elapsed=$(( $(now_ms) - start ))

    if [[ "$count" -ge "$MIN_CATALOGUE_APIS" ]]; then
        audit_line "AUDIT-5" "Catalogue >= ${MIN_CATALOGUE_APIS} APIs" "PASS" "" "$elapsed" "false"
    else
        audit_line "AUDIT-5" "Catalogue >= ${MIN_CATALOGUE_APIS} APIs" "FAIL" "got ${count}" "$elapsed" "false"
    fi
}

# AUDIT-6: Token acquisition for 3 personas (BLOCKING)
audit_6() {
    local start
    start=$(now_ms)
    local all_ok=true
    local detail_parts=()
    local has_credentials=false

    # Test each persona individually (no associative arrays for bash 3.2 compat)
    if [[ -n "$ALEX_USER" && -n "$ALEX_PASSWORD" ]]; then
        has_credentials=true
        local token
        token=$(get_token "$ALEX_USER" "$ALEX_PASSWORD")
        if [[ -z "$token" ]]; then
            all_ok=false
            detail_parts+=("alex=FAIL")
        else
            detail_parts+=("alex=OK")
        fi
    fi

    if [[ -n "$PARZIVAL_USER" && -n "$PARZIVAL_PASSWORD" ]]; then
        has_credentials=true
        local token
        token=$(get_token "$PARZIVAL_USER" "$PARZIVAL_PASSWORD")
        if [[ -z "$token" ]]; then
            all_ok=false
            detail_parts+=("parzival=FAIL")
        else
            detail_parts+=("parzival=OK")
        fi
    fi

    if [[ -n "$SORRENTO_USER" && -n "$SORRENTO_PASSWORD" ]]; then
        has_credentials=true
        local token
        token=$(get_token "$SORRENTO_USER" "$SORRENTO_PASSWORD")
        if [[ -z "$token" ]]; then
            all_ok=false
            detail_parts+=("sorrento=FAIL")
        else
            detail_parts+=("sorrento=OK")
        fi
    fi

    if [[ "$has_credentials" == "false" ]]; then
        local elapsed=$(( $(now_ms) - start ))
        audit_line "AUDIT-6" "Tokens (personas)" "FAIL" "no credentials in env" "$elapsed" "true"
        return
    fi

    local elapsed=$(( $(now_ms) - start ))
    local detail
    detail=$(IFS=', '; echo "${detail_parts[*]}")

    if [[ "$all_ok" == "true" ]]; then
        audit_line "AUDIT-6" "Tokens (personas)" "PASS" "" "$elapsed" "true"
    else
        audit_line "AUDIT-6" "Tokens (personas)" "FAIL" "$detail" "$elapsed" "true"
    fi
}

# AUDIT-7: DNS resolution for 4 subdomains
audit_7() {
    local start
    start=$(now_ms)
    local resolved=0
    local total=4
    local failed_hosts=()

    for sub in portal api mcp auth; do
        local host="${sub}.${BASE_DOMAIN}"
        # Strip port if present (dig doesn't support host:port)
        host="${host%%:*}"
        if dig +short "$host" 2>/dev/null | grep -q '.'; then
            ((resolved++))
        else
            failed_hosts+=("$host")
        fi
    done

    local elapsed=$(( $(now_ms) - start ))

    if [[ $resolved -eq $total ]]; then
        audit_line "AUDIT-7" "DNS ${resolved}/${total}" "PASS" "" "$elapsed" "false"
    else
        local detail="missing: ${failed_hosts[*]}"
        audit_line "AUDIT-7" "DNS ${resolved}/${total}" "FAIL" "$detail" "$elapsed" "false"
    fi
}

# AUDIT-8: TLS certificates valid (not expired)
audit_8() {
    local start
    start=$(now_ms)
    local valid=0
    local total=4
    local failed_hosts=()

    # Skip TLS check for non-https setups
    if [[ "$PROTO" != "https" ]]; then
        local elapsed=$(( $(now_ms) - start ))
        audit_line "AUDIT-8" "TLS certificates" "FAIL" "skipped (non-https)" "$elapsed" "false"
        return
    fi

    for sub in portal api mcp auth; do
        local host="${sub}.${BASE_DOMAIN}"
        # Check if the certificate is not expired
        local expiry
        expiry=$(echo | openssl s_client -servername "$host" -connect "${host}:443" 2>/dev/null \
            | openssl x509 -noout -enddate 2>/dev/null \
            | sed 's/notAfter=//')

        if [[ -n "$expiry" ]]; then
            # Compare expiry date to now
            local expiry_epoch
            local now_epoch
            # Use portable date parsing
            if date --version &>/dev/null 2>&1; then
                # GNU date
                expiry_epoch=$(date -d "$expiry" +%s 2>/dev/null || echo "0")
                now_epoch=$(date +%s)
            else
                # macOS date
                expiry_epoch=$(date -j -f "%b %d %T %Y %Z" "$expiry" +%s 2>/dev/null || echo "0")
                now_epoch=$(date +%s)
            fi

            if [[ "$expiry_epoch" -gt "$now_epoch" ]]; then
                ((valid++))
            else
                failed_hosts+=("${host}(expired)")
            fi
        else
            failed_hosts+=("${host}(no-cert)")
        fi
    done

    local elapsed=$(( $(now_ms) - start ))

    if [[ $valid -eq $total ]]; then
        audit_line "AUDIT-8" "TLS certificates" "PASS" "" "$elapsed" "false"
    else
        local detail="invalid: ${failed_hosts[*]}"
        audit_line "AUDIT-8" "TLS certificates" "FAIL" "$detail" "$elapsed" "false"
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    check_prereqs

    echo ""
    echo "================================================================"
    echo "  STOA Platform Smoke Test Gate (Level 1)"
    echo "  CAB-1043"
    echo "================================================================"
    echo ""
    echo "  Base Domain : ${BASE_DOMAIN}"
    echo "  Protocol    : ${PROTO}"
    echo "  Timestamp   : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo ""
    echo "----------------------------------------------------------------"
    echo ""

    # Run all 8 audits
    audit_1
    audit_2
    audit_3
    audit_4
    audit_5
    audit_6
    audit_7
    audit_8

    # Print results
    for line in "${RESULTS[@]}"; do
        echo "  $line"
    done

    echo ""
    echo "----------------------------------------------------------------"
    echo ""

    # Final verdict
    local score="${PASSED}/${TOTAL}"

    if [[ $FAILED -eq 0 ]]; then
        echo "  SCORE: ${score} -- GATE PASSED"
        echo ""
        exit 0
    else
        echo "  SCORE: ${score} -- GATE FAILED (minimum ${TOTAL}/${TOTAL})"
        if [[ $BLOCKING_FAILED -gt 0 ]]; then
            echo "  BLOCKING FAILURES: ${BLOCKING_FAILED} (AUDIT-1, AUDIT-2, or AUDIT-6)"
        fi
        echo ""
        exit 1
    fi
}

main "$@"
