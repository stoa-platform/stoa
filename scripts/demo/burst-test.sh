#!/bin/bash
# =============================================================================
# CAB-1104: Multi-Tenant Rate Limit Burst Test
# =============================================================================
# Tests that:
# - high-five tenant: 1000 req/min (should NOT trigger 429 with 150 requests)
# - ioi tenant: 100 req/min (should trigger 429 after ~100 requests)
# =============================================================================

set -e

# Configuration
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
HIGH_FIVE_TOKEN="${HIGH_FIVE_TOKEN:-}"
IOI_TOKEN="${IOI_TOKEN:-}"
REQUESTS_TO_SEND=150

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "CAB-1104: Multi-Tenant Rate Limit Test"
echo "========================================"
echo ""

# Function to count HTTP status codes
count_status_codes() {
    local results_file=$1
    local code_200=$(grep -c "^200$" "$results_file" 2>/dev/null || echo 0)
    local code_429=$(grep -c "^429$" "$results_file" 2>/dev/null || echo 0)
    local other=$(grep -v -e "^200$" -e "^429$" "$results_file" | wc -l | tr -d ' ')
    echo "$code_200 $code_429 $other"
}

# Function to run burst test for a tenant
run_burst_test() {
    local tenant=$1
    local token=$2
    local expected_429=$3
    local temp_file="/tmp/burst_test_${tenant}.txt"

    echo -e "${YELLOW}Testing tenant: ${tenant}${NC}"
    echo "Sending $REQUESTS_TO_SEND requests..."

    # Clear temp file
    > "$temp_file"

    # Send burst of requests
    for i in $(seq 1 $REQUESTS_TO_SEND); do
        if [ -n "$token" ]; then
            status=$(curl -s -o /dev/null -w "%{http_code}" \
                -H "Authorization: Bearer $token" \
                "${GATEWAY_URL}/tools/stoa_health_check")
        else
            status=$(curl -s -o /dev/null -w "%{http_code}" \
                "${GATEWAY_URL}/tools/stoa_health_check")
        fi
        echo "$status" >> "$temp_file"

        # Progress indicator every 50 requests
        if [ $((i % 50)) -eq 0 ]; then
            echo "  Sent $i requests..."
        fi
    done

    # Count results
    read code_200 code_429 other <<< $(count_status_codes "$temp_file")

    echo ""
    echo "Results for $tenant:"
    echo "  - 200 OK:           $code_200"
    echo "  - 429 Rate Limited: $code_429"
    echo "  - Other:            $other"

    if [ "$expected_429" = "yes" ] && [ "$code_429" -gt 0 ]; then
        echo -e "  ${GREEN}PASS: Rate limiting triggered as expected${NC}"
        return 0
    elif [ "$expected_429" = "no" ] && [ "$code_429" -eq 0 ]; then
        echo -e "  ${GREEN}PASS: No rate limiting (high limit tenant)${NC}"
        return 0
    else
        echo -e "  ${RED}FAIL: Unexpected result${NC}"
        return 1
    fi
}

# ============================================================================
# Test 1: HIGH-FIVE tenant (1000 req/min - should NOT rate limit)
# ============================================================================
echo ""
echo "========================================"
echo "Test 1: HIGH-FIVE (1000 req/min limit)"
echo "========================================"
if [ -z "$HIGH_FIVE_TOKEN" ]; then
    echo -e "${YELLOW}WARNING: HIGH_FIVE_TOKEN not set, using anonymous${NC}"
    echo "Set HIGH_FIVE_TOKEN env var to test with authentication"
fi
run_burst_test "high-five" "$HIGH_FIVE_TOKEN" "no" || HIGH_FIVE_RESULT="FAIL"

echo ""

# ============================================================================
# Test 2: IOI tenant (100 req/min - SHOULD rate limit)
# ============================================================================
echo "========================================"
echo "Test 2: IOI (100 req/min limit)"
echo "========================================"
if [ -z "$IOI_TOKEN" ]; then
    echo -e "${YELLOW}WARNING: IOI_TOKEN not set, using anonymous${NC}"
    echo "Set IOI_TOKEN env var to test with authentication"
fi
run_burst_test "ioi" "$IOI_TOKEN" "yes" || IOI_RESULT="FAIL"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "========================================"
echo "Summary"
echo "========================================"

if [ -z "$HIGH_FIVE_RESULT" ] && [ -z "$IOI_RESULT" ]; then
    echo -e "${GREEN}All tests PASSED!${NC}"
    echo ""
    echo "Multi-tenant rate limiting is working correctly:"
    echo "  - high-five: 1000 req/min (no throttling)"
    echo "  - ioi: 100 req/min (throttling visible)"
    exit 0
else
    echo -e "${RED}Some tests FAILED${NC}"
    exit 1
fi
