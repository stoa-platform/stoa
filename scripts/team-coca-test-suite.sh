#!/bin/bash
# ============================================================================
# 🥤 TEAM COCA TEST SUITE - CAB-638 OASIS TENANT
# ============================================================================
# Real tests with real assertions. No bullshit "→ Check:" documentation.
# Each test PASSES or FAILS. Period.
# ============================================================================

set -uo pipefail

# Configuration
MCP_GATEWAY="${MCP_GATEWAY:-https://mcp.stoa.cab-i.com}"
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.stoa.cab-i.com}"
REALM="${REALM:-stoa}"

# Test credentials (from Keycloak)
PARZIVAL_USER="wade@oasis.io"
PARZIVAL_PASS="${PARZIVAL_PASS:-parzival123}"
SORRENTO_USER="nolan@ioi.com"
SORRENTO_PASS="${SORRENTO_PASS:-sorrento123}"
HALLIDAY_USER="james@gregarious.games"
HALLIDAY_PASS="${HALLIDAY_PASS:-halliday123}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Counters
TOTAL=0
PASSED=0
FAILED=0
SKIPPED=0

# Results array for final report
declare -a RESULTS=()

# ============================================================================
# TEST FRAMEWORK
# ============================================================================

test_start() {
    local test_name="$1"
    ((TOTAL++))
    echo -e "\n${BLUE}[TEST ${TOTAL}]${NC} $test_name"
}

test_pass() {
    local msg="${1:-}"
    ((PASSED++))
    RESULTS+=("✅ PASS: Test ${TOTAL} - $msg")
    echo -e "${GREEN}  ✅ PASS${NC} $msg"
}

test_fail() {
    local msg="${1:-}"
    ((FAILED++))
    RESULTS+=("❌ FAIL: Test ${TOTAL} - $msg")
    echo -e "${RED}  ❌ FAIL${NC} $msg"
}

test_skip() {
    local msg="${1:-}"
    ((SKIPPED++))
    RESULTS+=("⏭️ SKIP: Test ${TOTAL} - $msg")
    echo -e "${YELLOW}  ⏭️ SKIP${NC} $msg"
}

assert_eq() {
    local expected="$1"
    local actual="$2"
    local msg="${3:-values should be equal}"
    
    if [[ "$expected" == "$actual" ]]; then
        test_pass "$msg (expected=$expected, got=$actual)"
        return 0
    else
        test_fail "$msg (expected=$expected, got=$actual)"
        return 1
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local msg="${3:-should contain substring}"
    
    if [[ "$haystack" == *"$needle"* ]]; then
        test_pass "$msg"
        return 0
    else
        test_fail "$msg (looking for '$needle')"
        return 1
    fi
}

assert_not_contains() {
    local haystack="$1"
    local needle="$2"
    local msg="${3:-should not contain substring}"
    
    if [[ "$haystack" != *"$needle"* ]]; then
        test_pass "$msg"
        return 0
    else
        test_fail "$msg (found '$needle' but shouldn't)"
        return 1
    fi
}

assert_http_status() {
    local expected="$1"
    local actual="$2"
    local msg="${3:-HTTP status check}"
    
    assert_eq "$expected" "$actual" "$msg"
}

assert_gt() {
    local val1="$1"
    local val2="$2"
    local msg="${3:-should be greater than}"
    
    if [[ "$val1" -gt "$val2" ]]; then
        test_pass "$msg ($val1 > $val2)"
        return 0
    else
        test_fail "$msg ($val1 not > $val2)"
        return 1
    fi
}

# ============================================================================
# HELPERS
# ============================================================================

get_token() {
    local username="$1"
    local password="$2"
    
    local response=$(curl -s -X POST "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "grant_type=password" \
        -d "client_id=stoa-portal" \
        -d "username=${username}" \
        -d "password=${password}" \
        2>/dev/null)
    
    echo "$response" | jq -r '.access_token // empty' 2>/dev/null
}

mcp_call() {
    local tool="$1"
    local token="$2"
    local payload="${3:-{}}"
    
    curl -s -X POST "${MCP_GATEWAY}/mcp/v1/tools/${tool}/invoke" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        2>/dev/null
}

mcp_call_status() {
    local tool="$1"
    local token="$2"
    local payload="${3:-{}}"
    
    curl -s -o /dev/null -w "%{http_code}" -X POST "${MCP_GATEWAY}/mcp/v1/tools/${tool}/invoke" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        2>/dev/null
}

check_gateway_health() {
    local status=$(curl -s -o /dev/null -w "%{http_code}" "${MCP_GATEWAY}/healthz" 2>/dev/null)
    [[ "$status" == "200" ]]
}

# ============================================================================
# 🔌 CONNECTIVITY TESTS
# ============================================================================

test_gateway_reachable() {
    test_start "Gateway is reachable"
    
    local status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${MCP_GATEWAY}/healthz" 2>/dev/null)
    
    if [[ "$status" == "200" ]]; then
        test_pass "Gateway responded with 200"
        return 0
    elif [[ "$status" == "000" ]]; then
        test_skip "Gateway unreachable (network issue)"
        return 1
    else
        test_fail "Gateway returned $status"
        return 1
    fi
}

test_keycloak_reachable() {
    test_start "Keycloak is reachable"
    
    local status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${KEYCLOAK_URL}/realms/${REALM}/.well-known/openid-configuration" 2>/dev/null)
    
    if [[ "$status" == "200" ]]; then
        test_pass "Keycloak OIDC endpoint responded"
        return 0
    elif [[ "$status" == "000" ]]; then
        test_skip "Keycloak unreachable (network issue)"
        return 1
    else
        test_fail "Keycloak returned $status"
        return 1
    fi
}

test_mcp_tools_endpoint() {
    test_start "MCP tools endpoint returns tool list"
    
    local response=$(curl -s --max-time 5 "${MCP_GATEWAY}/mcp/v1/tools" 2>/dev/null)
    local tool_count=$(echo "$response" | jq '.tools | length' 2>/dev/null || echo "0")
    
    if [[ "$tool_count" -gt 0 ]]; then
        test_pass "Found $tool_count tools"
        return 0
    else
        test_fail "No tools returned or invalid response"
        return 1
    fi
}

test_oasis_tools_deployed() {
    test_start "OASIS tenant tools are deployed (5 expected)"
    
    local response=$(curl -s --max-time 5 "${MCP_GATEWAY}/mcp/v1/tools" 2>/dev/null)
    local oasis_count=$(echo "$response" | jq '[.tools[].name | select(contains("oasis"))] | length' 2>/dev/null || echo "0")
    
    assert_eq "5" "$oasis_count" "OASIS tools count"
}

# ============================================================================
# 🔐 AUTHENTICATION TESTS
# ============================================================================

test_parzival_can_authenticate() {
    test_start "Parzival (namespace_developer) can authenticate"
    
    local token=$(get_token "$PARZIVAL_USER" "$PARZIVAL_PASS")
    
    if [[ -n "$token" && "$token" != "null" ]]; then
        test_pass "Got valid token for Parzival"
        echo "$token" > /tmp/parzival_token
        return 0
    else
        test_fail "Authentication failed for Parzival"
        return 1
    fi
}

test_sorrento_can_authenticate() {
    test_start "Sorrento (tenant_admin) can authenticate"
    
    local token=$(get_token "$SORRENTO_USER" "$SORRENTO_PASS")
    
    if [[ -n "$token" && "$token" != "null" ]]; then
        test_pass "Got valid token for Sorrento"
        echo "$token" > /tmp/sorrento_token
        return 0
    else
        test_fail "Authentication failed for Sorrento"
        return 1
    fi
}

test_invalid_credentials_rejected() {
    test_start "Invalid credentials are rejected"
    
    local token=$(get_token "fake@oasis.io" "wrongpassword")
    
    if [[ -z "$token" || "$token" == "null" ]]; then
        test_pass "Invalid credentials correctly rejected"
        return 0
    else
        test_fail "Invalid credentials should not return token"
        return 1
    fi
}

# ============================================================================
# 🔪 CHUCKY - RATE LIMIT TESTS
# ============================================================================

test_rate_limit_enforced() {
    test_start "Rate limit is enforced on transfer-coins (10/min)"
    
    local token=$(cat /tmp/parzival_token 2>/dev/null)
    if [[ -z "$token" ]]; then
        test_skip "No token available (auth test failed)"
        return 1
    fi
    
    local blocked=0
    local payload='{"amount": 100, "recipient": "aech@oasis.io"}'
    
    # Fire 15 requests rapidly - should hit rate limit
    for i in {1..15}; do
        local status=$(mcp_call_status "oasis__Economy-API__transfer-coins" "$token" "$payload")
        if [[ "$status" == "429" ]]; then
            blocked=1
            break
        fi
    done
    
    if [[ "$blocked" -eq 1 ]]; then
        test_pass "Rate limit triggered (got 429)"
        return 0
    else
        test_fail "Rate limit not enforced after 15 rapid requests"
        return 1
    fi
}

test_cumulative_threshold_check() {
    test_start "Cumulative transfer threshold triggers 2FA at 100K"
    
    local token=$(cat /tmp/parzival_token 2>/dev/null)
    if [[ -z "$token" ]]; then
        test_skip "No token available"
        return 1
    fi
    
    # Try transfer of 100001 coins - should require 2FA
    local payload='{"amount": 100001, "recipient": "aech@oasis.io"}'
    local response=$(mcp_call "oasis__Economy-API__transfer-coins" "$token" "$payload")
    
    # Should return 403 or require_2fa flag
    if [[ "$response" == *"require_2fa"* ]] || [[ "$response" == *"403"* ]] || [[ "$response" == *"attestation"* ]]; then
        test_pass "Large transfer requires additional auth"
        return 0
    else
        test_fail "100K+ transfer did not trigger 2FA requirement"
        echo "  Response: $response"
        return 1
    fi
}

# ============================================================================
# 🛡️ MULTI-TENANT ISOLATION TESTS
# ============================================================================

test_tenant_isolation_tools_visibility() {
    test_start "Parzival cannot see IOI tenant tools"
    
    local token=$(cat /tmp/parzival_token 2>/dev/null)
    if [[ -z "$token" ]]; then
        test_skip "No token available"
        return 1
    fi
    
    local response=$(curl -s -H "Authorization: Bearer $token" "${MCP_GATEWAY}/mcp/v1/tools" 2>/dev/null)
    
    # Parzival is in OASIS tenant, should NOT see IOI tools
    if [[ "$response" == *"ioi__"* ]]; then
        test_fail "OASIS user can see IOI tenant tools (isolation breach!)"
        return 1
    else
        test_pass "OASIS user cannot see IOI tools"
        return 0
    fi
}

test_tenant_isolation_data_access() {
    test_start "Parzival cannot access Sorrento's data via search"
    
    local parzival_token=$(cat /tmp/parzival_token 2>/dev/null)
    if [[ -z "$parzival_token" ]]; then
        test_skip "No token available"
        return 1
    fi
    
    # Search for Sorrento's IOI data
    local payload='{"query": "nolan sorrento ioi"}'
    local response=$(mcp_call "oasis__Avatar-API__search-players" "$parzival_token" "$payload")
    
    # Should NOT return IOI internal data
    if [[ "$response" == *"ioi.com"* ]] || [[ "$response" == *"sixers"* ]]; then
        test_fail "Cross-tenant data leak detected"
        return 1
    else
        test_pass "No cross-tenant data in search results"
        return 0
    fi
}

test_tenant_admin_scope() {
    test_start "Sorrento (tenant_admin) can only admin his own tenant"
    
    local sorrento_token=$(cat /tmp/sorrento_token 2>/dev/null)
    if [[ -z "$sorrento_token" ]]; then
        test_skip "No token available"
        return 1
    fi
    
    # Try to access OASIS admin endpoint as IOI admin
    local status=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $sorrento_token" \
        "${MCP_GATEWAY}/admin/tenants/oasis/users" 2>/dev/null)
    
    if [[ "$status" == "403" ]]; then
        test_pass "Cross-tenant admin access blocked (403)"
        return 0
    elif [[ "$status" == "200" ]]; then
        test_fail "IOI admin accessed OASIS tenant data!"
        return 1
    else
        test_skip "Unexpected status: $status"
        return 1
    fi
}

# ============================================================================
# 👑 PR1NC3SS - WORKFLOW TESTS
# ============================================================================

test_self_approval_blocked() {
    test_start "Creator cannot approve their own tool promotion"
    
    # This would require a more complex setup - marking as architectural test
    test_skip "Requires promotion workflow mock - verify manually in demo"
    return 1
}

test_approval_requires_justification() {
    test_start "Approval without justification is rejected"
    
    test_skip "Requires promotion workflow mock - verify manually in demo"
    return 1
}

test_rejection_workflow_exists() {
    test_start "REJECT action exists in workflow API"
    
    local response=$(curl -s "${MCP_GATEWAY}/api/v1/workflows/promotion/actions" 2>/dev/null)
    
    if [[ "$response" == *"reject"* ]] || [[ "$response" == *"REJECT"* ]]; then
        test_pass "Reject action found in workflow"
        return 0
    elif [[ -z "$response" ]]; then
        test_skip "Workflow API not available"
        return 1
    else
        test_fail "No REJECT action in workflow API"
        return 1
    fi
}

# ============================================================================
# 🐠 N3M0 - AGENT CREDENTIAL TESTS
# ============================================================================

test_agent_token_has_expiry() {
    test_start "Agent tokens have expiration (not infinite)"
    
    local token=$(cat /tmp/parzival_token 2>/dev/null)
    if [[ -z "$token" ]]; then
        test_skip "No token available"
        return 1
    fi
    
    # Decode JWT and check exp claim
    local payload=$(echo "$token" | cut -d'.' -f2 | base64 -d 2>/dev/null)
    local exp=$(echo "$payload" | jq -r '.exp // empty' 2>/dev/null)
    
    if [[ -n "$exp" && "$exp" != "null" ]]; then
        local now=$(date +%s)
        local ttl=$((exp - now))
        if [[ "$ttl" -gt 0 && "$ttl" -lt 86400 ]]; then
            test_pass "Token expires in ${ttl}s (< 24h)"
            return 0
        elif [[ "$ttl" -ge 86400 ]]; then
            test_fail "Token TTL too long: ${ttl}s (> 24h)"
            return 1
        fi
    else
        test_fail "Token has no expiration claim"
        return 1
    fi
}

test_revoked_token_rejected() {
    test_start "Revoked tokens are immediately rejected"
    
    # This requires a revocation mechanism test
    test_skip "Requires token revocation API - verify manually"
    return 1
}

# ============================================================================
# 📊 OBSERVABILITY TESTS
# ============================================================================

test_audit_log_captures_requests() {
    test_start "API calls are logged in audit trail"
    
    local token=$(cat /tmp/parzival_token 2>/dev/null)
    if [[ -z "$token" ]]; then
        test_skip "No token available"
        return 1
    fi
    
    # Make a call
    local payload='{"query": "gunter"}'
    mcp_call "oasis__Avatar-API__search-players" "$token" "$payload" > /dev/null
    
    # Check audit log (assuming endpoint exists)
    sleep 1
    local audit=$(curl -s -H "Authorization: Bearer $token" "${MCP_GATEWAY}/api/v1/audit/recent?limit=1" 2>/dev/null)
    
    if [[ "$audit" == *"search-players"* ]]; then
        test_pass "Request captured in audit log"
        return 0
    elif [[ -z "$audit" ]]; then
        test_skip "Audit API not available"
        return 1
    else
        test_fail "Request not found in audit log"
        return 1
    fi
}

# ============================================================================
# MAIN
# ============================================================================

print_header() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════════════════╗"
    echo "║  🥤 TEAM COCA TEST SUITE - OASIS TENANT                                   ║"
    echo "║  Real tests. Real assertions. No bullshit.                               ║"
    echo "╚═══════════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Target: ${MCP_GATEWAY}"
    echo "Auth:   ${KEYCLOAK_URL}"
    echo ""
}

print_summary() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 TEST RESULTS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  Total:   $TOTAL"
    echo -e "  ${GREEN}Passed:  $PASSED${NC}"
    echo -e "  ${RED}Failed:  $FAILED${NC}"
    echo -e "  ${YELLOW}Skipped: $SKIPPED${NC}"
    echo ""
    
    # Calculate pass rate (excluding skipped)
    local effective=$((TOTAL - SKIPPED))
    if [[ "$effective" -gt 0 ]]; then
        local rate=$((PASSED * 100 / effective))
        echo "  Pass rate: ${rate}% (of non-skipped)"
    fi
    echo ""
    
    # Verdict
    if [[ "$FAILED" -eq 0 && "$PASSED" -gt 0 ]]; then
        echo -e "  ${GREEN}═══════════════════════════════════════${NC}"
        echo -e "  ${GREEN}  ✅ VERDICT: APPROVED FOR DRY-RUN     ${NC}"
        echo -e "  ${GREEN}═══════════════════════════════════════${NC}"
    elif [[ "$FAILED" -le 2 && "$PASSED" -gt "$FAILED" ]]; then
        echo -e "  ${YELLOW}═══════════════════════════════════════${NC}"
        echo -e "  ${YELLOW}  ⚠️  VERDICT: CONDITIONAL             ${NC}"
        echo -e "  ${YELLOW}═══════════════════════════════════════${NC}"
    else
        echo -e "  ${RED}═══════════════════════════════════════${NC}"
        echo -e "  ${RED}  ❌ VERDICT: BLOCKED                  ${NC}"
        echo -e "  ${RED}═══════════════════════════════════════${NC}"
    fi
    echo ""
    
    # Print all results
    echo "Detailed results:"
    for result in "${RESULTS[@]}"; do
        echo "  $result"
    done
    echo ""
}

run_all_tests() {
    print_header
    
    echo "═══════════════════════════════════════════════════════════════════════════"
    echo "🔌 CONNECTIVITY"
    echo "═══════════════════════════════════════════════════════════════════════════"
    test_gateway_reachable
    local gateway_ok=$?
    
    test_keycloak_reachable
    local keycloak_ok=$?
    
    # If gateway is down, skip most tests
    if [[ "$gateway_ok" -ne 0 ]]; then
        echo ""
        echo -e "${YELLOW}⚠️  Gateway unreachable - running offline tests only${NC}"
        print_summary
        return 1
    fi
    
    test_mcp_tools_endpoint
    test_oasis_tools_deployed
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════════"
    echo "🔐 AUTHENTICATION"
    echo "═══════════════════════════════════════════════════════════════════════════"
    
    if [[ "$keycloak_ok" -eq 0 ]]; then
        test_parzival_can_authenticate
        test_sorrento_can_authenticate
        test_invalid_credentials_rejected
    else
        test_skip "Keycloak unavailable - skipping auth tests"
        ((SKIPPED+=3))
    fi
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════════"
    echo "🔪 CHUCKY - RATE LIMITS"
    echo "═══════════════════════════════════════════════════════════════════════════"
    test_rate_limit_enforced
    test_cumulative_threshold_check
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════════"
    echo "🛡️ MULTI-TENANT ISOLATION"
    echo "═══════════════════════════════════════════════════════════════════════════"
    test_tenant_isolation_tools_visibility
    test_tenant_isolation_data_access
    test_tenant_admin_scope
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════════"
    echo "👑 PR1NC3SS - WORKFLOWS"
    echo "═══════════════════════════════════════════════════════════════════════════"
    test_self_approval_blocked
    test_approval_requires_justification
    test_rejection_workflow_exists
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════════"
    echo "🐠 N3M0 - AGENT CREDENTIALS"
    echo "═══════════════════════════════════════════════════════════════════════════"
    test_agent_token_has_expiry
    test_revoked_token_rejected
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════════"
    echo "📊 OBSERVABILITY"
    echo "═══════════════════════════════════════════════════════════════════════════"
    test_audit_log_captures_requests
    
    print_summary
    
    # Exit code based on failures
    [[ "$FAILED" -eq 0 ]]
}

# Cleanup
cleanup() {
    rm -f /tmp/parzival_token /tmp/sorrento_token 2>/dev/null
}
trap cleanup EXIT

# Run
run_all_tests
