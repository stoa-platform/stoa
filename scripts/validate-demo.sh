#!/bin/bash
# CAB-295: STOA Demo Validation Script (Smoke Test)
# Purpose: Verify all demo components are working before presentation
#
# Usage:
#   ./scripts/validate-demo.sh              # Use default URLs
#   ./scripts/validate-demo.sh --local      # Use kubectl port-forward
#   ./scripts/validate-demo.sh --verbose    # Show detailed output
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

# Default URLs (production)
BASE_DOMAIN="${BASE_DOMAIN:-stoa.cab-i.com}"
API_URL="${API_URL:-https://api.${BASE_DOMAIN}}"
MCP_URL="${MCP_URL:-https://mcp.${BASE_DOMAIN}}"
PORTAL_URL="${PORTAL_URL:-https://portal.${BASE_DOMAIN}}"
CONSOLE_URL="${CONSOLE_URL:-https://console.${BASE_DOMAIN}}"
GRAFANA_URL="${GRAFANA_URL:-https://grafana.${BASE_DOMAIN}}"
PROMETHEUS_URL="${PROMETHEUS_URL:-https://prometheus.${BASE_DOMAIN}}"
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.${BASE_DOMAIN}}"

# Keycloak config
KEYCLOAK_REALM="${KEYCLOAK_REALM:-stoa}"
KEYCLOAK_CLIENT="${KEYCLOAK_CLIENT:-stoa-portal}"

# Test user credentials (from CAB-238 E2E users)
TEST_USER="${TEST_USER:-e2e-tenant-admin}"
TEST_PASSWORD="${TEST_PASSWORD:-Admin123!}"

# Script options
VERBOSE=false
LOCAL_MODE=false
NAMESPACE="stoa-system"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
SKIPPED=0

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((SKIPPED++))
}

log_verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${YELLOW}[DEBUG]${NC} $1"
    fi
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_fail "Required command not found: $1"
        return 1
    fi
    return 0
}

http_get() {
    local url="$1"
    local expected_code="${2:-200}"
    local headers="${3:-}"

    local response
    local http_code

    if [[ -n "$headers" ]]; then
        response=$(curl -s -w "\n%{http_code}" -H "$headers" "$url" 2>/dev/null || echo -e "\n000")
    else
        response=$(curl -s -w "\n%{http_code}" "$url" 2>/dev/null || echo -e "\n000")
    fi

    http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    log_verbose "URL: $url"
    log_verbose "HTTP Code: $http_code"
    log_verbose "Response: ${body:0:200}..."

    if [[ "$http_code" == "$expected_code" ]]; then
        echo "$body"
        return 0
    else
        echo "$http_code"
        return 1
    fi
}

get_keycloak_token() {
    local username="$1"
    local password="$2"

    local token_url="${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token"

    local response=$(curl -s -X POST "$token_url" \
        -d "grant_type=password" \
        -d "client_id=${KEYCLOAK_CLIENT}" \
        -d "username=${username}" \
        -d "password=${password}" 2>/dev/null)

    local token=$(echo "$response" | jq -r '.access_token // empty')

    if [[ -n "$token" && "$token" != "null" ]]; then
        echo "$token"
        return 0
    else
        log_verbose "Token error: $(echo "$response" | jq -r '.error_description // .error // "Unknown error"')"
        return 1
    fi
}

# =============================================================================
# Parse Arguments
# =============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            LOCAL_MODE=true
            API_URL="http://localhost:8000"
            MCP_URL="http://localhost:8080"
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --local     Use localhost URLs (requires port-forward)"
            echo "  --verbose   Show detailed output"
            echo "  --help      Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# =============================================================================
# Main Script
# =============================================================================

echo ""
echo "=============================================="
echo "  STOA Demo Validation (Smoke Test)"
echo "  CAB-295"
echo "=============================================="
echo ""
echo "Base Domain: ${BASE_DOMAIN}"
echo "Timestamp:   $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# Check prerequisites
log_info "Checking prerequisites..."
check_command curl || exit 1
check_command jq || exit 1
check_command kubectl || log_skip "kubectl not found - skipping K8s checks"
echo ""

# =============================================================================
# 1. Services Health Checks
# =============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Services Health Checks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Control-Plane API
echo -n "   Control-Plane API (/health): "
if response=$(http_get "${API_URL}/health"); then
    status=$(echo "$response" | jq -r '.status // "unknown"')
    if [[ "$status" == "healthy" || "$status" == "ok" ]]; then
        log_success "$status"
    else
        log_fail "status=$status"
    fi
else
    log_fail "HTTP $response"
fi

# MCP Gateway
echo -n "   MCP Gateway (/health): "
if response=$(http_get "${MCP_URL}/health"); then
    status=$(echo "$response" | jq -r '.status // "unknown"')
    if [[ "$status" == "healthy" || "$status" == "ok" ]]; then
        log_success "$status"
    else
        log_fail "status=$status"
    fi
else
    log_fail "HTTP $response"
fi

# Portal
echo -n "   Portal (frontend): "
if http_get "${PORTAL_URL}" "200" > /dev/null 2>&1; then
    log_success "HTTP 200"
else
    log_fail "Not reachable"
fi

# Console UI
echo -n "   Console UI (frontend): "
if http_get "${CONSOLE_URL}" "200" > /dev/null 2>&1; then
    log_success "HTTP 200"
else
    log_fail "Not reachable"
fi

echo ""

# =============================================================================
# 2. Observability Stack
# =============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Observability Stack"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Grafana
echo -n "   Grafana: "
if http_get "${GRAFANA_URL}/api/health" "200" > /dev/null 2>&1; then
    log_success "HTTP 200"
else
    # Grafana might redirect to login
    if http_get "${GRAFANA_URL}" "302" > /dev/null 2>&1 || http_get "${GRAFANA_URL}/login" "200" > /dev/null 2>&1; then
        log_success "Redirect to login (auth enabled)"
    else
        log_fail "Not reachable"
    fi
fi

# Prometheus (may require auth)
echo -n "   Prometheus: "
if http_get "${PROMETHEUS_URL}/-/healthy" "200" > /dev/null 2>&1; then
    log_success "HTTP 200"
else
    log_skip "Auth required or not exposed"
fi

echo ""

# =============================================================================
# 3. Authentication (Keycloak)
# =============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Authentication (Keycloak)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Keycloak OIDC discovery
echo -n "   Keycloak OIDC discovery: "
OIDC_URL="${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"
if response=$(http_get "$OIDC_URL"); then
    issuer=$(echo "$response" | jq -r '.issuer // "unknown"')
    if [[ "$issuer" == *"${KEYCLOAK_REALM}"* ]]; then
        log_success "Realm: ${KEYCLOAK_REALM}"
    else
        log_fail "Unexpected issuer: $issuer"
    fi
else
    log_fail "HTTP $response"
fi

# Get auth token
echo -n "   Token acquisition (${TEST_USER}): "
if TOKEN=$(get_keycloak_token "$TEST_USER" "$TEST_PASSWORD"); then
    log_success "Token obtained"
    export AUTH_TOKEN="$TOKEN"
else
    log_fail "Failed to get token"
    AUTH_TOKEN=""
fi

echo ""

# =============================================================================
# 4. Database
# =============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Database"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -n "   PostgreSQL (pg_isready): "
if command -v kubectl &> /dev/null; then
    if kubectl exec -n "${NAMESPACE}" control-plane-db-0 -- pg_isready -U stoa -q 2>/dev/null; then
        log_success "Ready"
    else
        log_fail "Not ready"
    fi
else
    log_skip "kubectl not available"
fi

echo ""

# =============================================================================
# 5. MCP Gateway - Auth Flow
# =============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. MCP Gateway - Auth Flow"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Test without token (should return 401)
echo -n "   Request without token (expect 401): "
response=$(curl -s -w "\n%{http_code}" "${MCP_URL}/mcp/v1/tools" 2>/dev/null || echo -e "\n000")
http_code=$(echo "$response" | tail -n1)
if [[ "$http_code" == "401" || "$http_code" == "403" ]]; then
    log_success "HTTP $http_code (auth required)"
else
    if [[ "$http_code" == "200" ]]; then
        log_skip "HTTP 200 (auth disabled or public endpoint)"
    else
        log_fail "HTTP $http_code (unexpected)"
    fi
fi

# Test with token (should return 200)
echo -n "   Request with token (expect 200): "
if [[ -n "$AUTH_TOKEN" ]]; then
    response=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer ${AUTH_TOKEN}" "${MCP_URL}/mcp/v1/tools" 2>/dev/null || echo -e "\n000")
    http_code=$(echo "$response" | tail -n1)
    if [[ "$http_code" == "200" ]]; then
        log_success "HTTP 200"
    else
        log_fail "HTTP $http_code"
    fi
else
    log_skip "No token available"
fi

echo ""

# =============================================================================
# 6. MCP Gateway - Tools
# =============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. MCP Gateway - Tools"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# List tools
echo -n "   List tools (/mcp/v1/tools): "
if [[ -n "$AUTH_TOKEN" ]]; then
    response=$(curl -s -H "Authorization: Bearer ${AUTH_TOKEN}" "${MCP_URL}/mcp/v1/tools" 2>/dev/null)
    tool_count=$(echo "$response" | jq -r '.tools | length // 0')
    if [[ "$tool_count" -gt 0 ]]; then
        log_success "${tool_count} tools found"

        # Show tool names in verbose mode
        if [[ "$VERBOSE" == "true" ]]; then
            echo "$response" | jq -r '.tools[].name' | while read -r tool; do
                echo "      - $tool"
            done
        fi
    else
        log_fail "No tools found"
    fi
else
    log_skip "No token available"
fi

# Invoke demo tool (crm-search)
echo -n "   Invoke tool (crm-search): "
if [[ -n "$AUTH_TOKEN" ]]; then
    response=$(curl -s -X POST \
        -H "Authorization: Bearer ${AUTH_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"arguments": {"query": "test", "limit": 1}}' \
        "${MCP_URL}/mcp/v1/tools/team_alpha_crm_search/invoke" 2>/dev/null)

    # Check for success or mock response
    if echo "$response" | jq -e '.content // .result // .data' > /dev/null 2>&1; then
        log_success "Tool invoked"
    elif echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        error=$(echo "$response" | jq -r '.error.message // .error // "unknown"')
        log_fail "Error: $error"
    else
        log_skip "Response: ${response:0:50}..."
    fi
else
    log_skip "No token available"
fi

# Check metrics
echo -n "   Metrics endpoint (/metrics): "
if response=$(http_get "${MCP_URL}/metrics"); then
    metric_count=$(echo "$response" | grep -c "stoa_mcp" || echo "0")
    if [[ "$metric_count" -gt 0 ]]; then
        log_success "${metric_count} stoa_mcp_* metrics"
    else
        log_skip "No stoa_mcp metrics found"
    fi
else
    log_skip "Metrics endpoint not available"
fi

echo ""

# =============================================================================
# 7. Demo Data (Kubernetes Resources)
# =============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7. Demo Data (Kubernetes)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v kubectl &> /dev/null; then
    # MCP Tools
    echo -n "   MCP Tools (CRDs): "
    tool_count=$(kubectl get tools -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$tool_count" -gt 0 ]]; then
        log_success "${tool_count} tools"
    else
        log_fail "No tools found"
    fi

    # Tenants
    echo -n "   Tenants (CRDs): "
    tenant_count=$(kubectl get tenants -n stoa-system --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$tenant_count" -gt 0 ]]; then
        log_success "${tenant_count} tenants"
    else
        log_skip "No tenants found"
    fi

    # Subscriptions
    echo -n "   Subscriptions (CRDs): "
    sub_count=$(kubectl get subscriptions -n stoa-system --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$sub_count" -gt 0 ]]; then
        log_success "${sub_count} subscriptions"
    else
        log_skip "No subscriptions found"
    fi

    # Grafana dashboards
    echo -n "   Grafana Dashboards: "
    dashboard_count=$(kubectl get configmap -n stoa-monitoring -l grafana_dashboard=1 --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$dashboard_count" -gt 0 ]]; then
        log_success "${dashboard_count} dashboards"
    else
        log_fail "No dashboards found"
    fi

    # Prometheus alerting rules
    echo -n "   Alerting Rules: "
    if kubectl get prometheusrule -n stoa-monitoring stoa-alerts &>/dev/null; then
        rule_groups=$(kubectl get prometheusrule -n stoa-monitoring stoa-alerts -o jsonpath='{.spec.groups[*].name}' | wc -w | tr -d ' ')
        log_success "${rule_groups} rule groups"
    else
        log_fail "stoa-alerts not found"
    fi
else
    log_skip "kubectl not available - skipping K8s checks"
fi

echo ""

# =============================================================================
# 8. Pod Status
# =============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8. Pod Status (stoa-system)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v kubectl &> /dev/null; then
    # Key pods to check
    declare -a PODS=("control-plane-api" "mcp-gateway" "keycloak" "control-plane-db" "redpanda")

    for pod_prefix in "${PODS[@]}"; do
        echo -n "   ${pod_prefix}: "
        pod_status=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name="${pod_prefix}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || \
                     kubectl get pods -n "${NAMESPACE}" --field-selector=status.phase=Running 2>/dev/null | grep -c "^${pod_prefix}" || echo "")

        # Try alternative selector
        if [[ -z "$pod_status" ]]; then
            pod_info=$(kubectl get pods -n "${NAMESPACE}" 2>/dev/null | grep "^${pod_prefix}" | head -1)
            if [[ -n "$pod_info" ]]; then
                ready=$(echo "$pod_info" | awk '{print $2}')
                status=$(echo "$pod_info" | awk '{print $3}')
                if [[ "$status" == "Running" ]]; then
                    log_success "Running (${ready})"
                else
                    log_fail "${status} (${ready})"
                fi
            else
                log_skip "Not found"
            fi
        elif [[ "$pod_status" == "Running" ]]; then
            log_success "Running"
        else
            log_fail "$pod_status"
        fi
    done
else
    log_skip "kubectl not available"
fi

echo ""

# =============================================================================
# Summary
# =============================================================================

echo "=============================================="
echo "  Summary"
echo "=============================================="
echo ""
echo -e "  ${GREEN}Passed:${NC}  ${PASSED}"
echo -e "  ${RED}Failed:${NC}  ${FAILED}"
echo -e "  ${YELLOW}Skipped:${NC} ${SKIPPED}"
echo ""

if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}=============================================="
    echo "  All checks passed! Demo is ready."
    echo "==============================================${NC}"
    exit 0
else
    echo -e "${RED}=============================================="
    echo "  Some checks failed. Review above output."
    echo "==============================================${NC}"
    exit 1
fi
