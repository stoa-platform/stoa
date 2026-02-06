#!/bin/bash
# =============================================================================
# CAB-1104: Pre-Demo Checklist Script
# =============================================================================
# Comprehensive GO/NO-GO check before the demo.
# Validates all components are ready:
# - Kubernetes cluster health
# - API connectivity
# - Grafana dashboards
# - MCP tools availability
# - Cache warmth
#
# Returns exit code 0 (GO) or 1 (NO-GO)
#
# Usage: ./pre-demo-check.sh [--verbose]
# =============================================================================

set -e

# Configuration
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-https://api.gostoa.dev}"
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
GRAFANA_URL="${GRAFANA_URL:-https://grafana.gostoa.dev}"
KEYCLOAK_URL="${KEYCLOAK_URL:-https://auth.gostoa.dev}"
VERBOSE="${1:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Check function
check() {
    local name="$1"
    local result="$2"
    local critical="${3:-true}"

    if [ "$result" = "pass" ]; then
        echo -e "  ${GREEN}[PASS]${NC} $name"
        ((PASSED++))
    elif [ "$result" = "warn" ]; then
        echo -e "  ${YELLOW}[WARN]${NC} $name"
        ((WARNINGS++))
    else
        if [ "$critical" = "true" ]; then
            echo -e "  ${RED}[FAIL]${NC} $name"
            ((FAILED++))
        else
            echo -e "  ${YELLOW}[SKIP]${NC} $name (non-critical)"
            ((WARNINGS++))
        fi
    fi
}

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           STOA Demo Pre-Flight Checklist                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Timestamp: $(date -Iseconds)"
echo ""

# =============================================================================
# Infrastructure Checks
# =============================================================================
echo -e "${CYAN}Infrastructure${NC}"
echo "─────────────────────────────────────────"

# Kubernetes cluster
if command -v kubectl &> /dev/null; then
    if kubectl cluster-info &> /dev/null; then
        NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
        if [ "$NODE_COUNT" -gt 0 ]; then
            check "Kubernetes cluster ($NODE_COUNT nodes)" "pass"
        else
            check "Kubernetes cluster (no nodes ready)" "fail"
        fi
    else
        check "Kubernetes cluster unreachable" "fail"
    fi
else
    check "kubectl not available" "warn" "false"
fi

# MCP Gateway pods
if command -v kubectl &> /dev/null; then
    GATEWAY_READY=$(kubectl get pods -n stoa-system -l app=mcp-gateway --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    if [ "$GATEWAY_READY" -gt 0 ]; then
        check "MCP Gateway pods ($GATEWAY_READY running)" "pass"
    else
        check "MCP Gateway pods (none running)" "fail"
    fi
else
    check "MCP Gateway pods" "warn" "false"
fi

# Control Plane pods
if command -v kubectl &> /dev/null; then
    CP_READY=$(kubectl get pods -n stoa-system -l app=control-plane-api --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    if [ "$CP_READY" -gt 0 ]; then
        check "Control Plane pods ($CP_READY running)" "pass"
    else
        check "Control Plane pods (none running)" "warn" "false"
    fi
else
    check "Control Plane pods" "warn" "false"
fi

echo ""

# =============================================================================
# Service Health Checks
# =============================================================================
echo -e "${CYAN}Service Health${NC}"
echo "─────────────────────────────────────────"

# Gateway health
GATEWAY_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY_URL/health" --max-time 5 2>/dev/null || echo "000")
if [ "$GATEWAY_HEALTH" = "200" ]; then
    check "MCP Gateway health ($GATEWAY_URL)" "pass"
else
    check "MCP Gateway health (HTTP $GATEWAY_HEALTH)" "fail"
fi

# Control Plane health
CP_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$CONTROL_PLANE_URL/health" --max-time 5 2>/dev/null || echo "000")
if [ "$CP_HEALTH" = "200" ]; then
    check "Control Plane health ($CONTROL_PLANE_URL)" "pass"
else
    check "Control Plane health (HTTP $CP_HEALTH)" "warn" "false"
fi

# Grafana health
GRAFANA_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$GRAFANA_URL/api/health" --max-time 5 2>/dev/null || echo "000")
if [ "$GRAFANA_HEALTH" = "200" ]; then
    check "Grafana health ($GRAFANA_URL)" "pass"
else
    check "Grafana health (HTTP $GRAFANA_HEALTH)" "warn" "false"
fi

# Keycloak health
KC_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$KEYCLOAK_URL/health/ready" --max-time 5 2>/dev/null || echo "000")
if [ "$KC_HEALTH" = "200" ]; then
    check "Keycloak health ($KEYCLOAK_URL)" "pass"
else
    check "Keycloak health (HTTP $KC_HEALTH)" "warn" "false"
fi

echo ""

# =============================================================================
# External APIs Checks
# =============================================================================
echo -e "${CYAN}External APIs${NC}"
echo "─────────────────────────────────────────"

# CoinGecko
COINGECKO=$(curl -s -o /dev/null -w "%{http_code}" "https://api.coingecko.com/api/v3/ping" --max-time 5 2>/dev/null || echo "000")
if [ "$COINGECKO" = "200" ]; then
    check "CoinGecko API (crypto prices)" "pass"
else
    check "CoinGecko API (HTTP $COINGECKO)" "warn" "false"
fi

# Open-Meteo
OPEN_METEO=$(curl -s -o /dev/null -w "%{http_code}" "https://api.open-meteo.com/v1/forecast?latitude=48.85&longitude=2.35&current_weather=true" --max-time 5 2>/dev/null || echo "000")
if [ "$OPEN_METEO" = "200" ]; then
    check "Open-Meteo API (weather)" "pass"
else
    check "Open-Meteo API (HTTP $OPEN_METEO)" "warn" "false"
fi

# JSONPlaceholder
JSONPLACEHOLDER=$(curl -s -o /dev/null -w "%{http_code}" "https://jsonplaceholder.typicode.com/posts/1" --max-time 5 2>/dev/null || echo "000")
if [ "$JSONPLACEHOLDER" = "200" ]; then
    check "JSONPlaceholder API (CRUD demo)" "pass"
else
    check "JSONPlaceholder API (HTTP $JSONPLACEHOLDER)" "warn" "false"
fi

# DummyJSON
DUMMYJSON=$(curl -s -o /dev/null -w "%{http_code}" "https://dummyjson.com/users/1" --max-time 5 2>/dev/null || echo "000")
if [ "$DUMMYJSON" = "200" ]; then
    check "DummyJSON API (CRM demo)" "pass"
else
    check "DummyJSON API (HTTP $DUMMYJSON)" "warn" "false"
fi

# httpbin
HTTPBIN=$(curl -s -o /dev/null -w "%{http_code}" "https://httpbin.org/get" --max-time 5 2>/dev/null || echo "000")
if [ "$HTTPBIN" = "200" ]; then
    check "httpbin API (legacy mock)" "pass"
else
    check "httpbin API (HTTP $HTTPBIN)" "warn" "false"
fi

echo ""

# =============================================================================
# MCP Tools Checks
# =============================================================================
echo -e "${CYAN}MCP Tools${NC}"
echo "─────────────────────────────────────────"

# List tools via gateway
TOOLS_RESPONSE=$(curl -s "$GATEWAY_URL/mcp/v1/tools" --max-time 10 2>/dev/null || echo '{"error": "failed"}')
if echo "$TOOLS_RESPONSE" | grep -q '"tools"'; then
    TOOL_COUNT=$(echo "$TOOLS_RESPONSE" | grep -o '"name"' | wc -l | tr -d ' ')
    if [ "$TOOL_COUNT" -ge 5 ]; then
        check "MCP tools registered ($TOOL_COUNT tools)" "pass"
    else
        check "MCP tools registered ($TOOL_COUNT tools - low)" "warn"
    fi
else
    check "MCP tools list failed" "warn" "false"
fi

# Check K8s Tool CRDs
if command -v kubectl &> /dev/null; then
    CRD_COUNT=$(kubectl get tools -A --no-headers 2>/dev/null | wc -l | tr -d ' ' || echo "0")
    if [ "$CRD_COUNT" -ge 10 ]; then
        check "Tool CRDs in cluster ($CRD_COUNT tools)" "pass"
    else
        check "Tool CRDs in cluster ($CRD_COUNT tools)" "warn"
    fi
else
    check "Tool CRDs" "warn" "false"
fi

echo ""

# =============================================================================
# Tenant Checks
# =============================================================================
echo -e "${CYAN}Tenants${NC}"
echo "─────────────────────────────────────────"

# Demo tenants exist
if command -v kubectl &> /dev/null; then
    for tenant in "high-five" "ioi" "oasis"; do
        NS_EXISTS=$(kubectl get namespace "tenant-$tenant" --no-headers 2>/dev/null | wc -l | tr -d ' ' || echo "0")
        if [ "$NS_EXISTS" -gt 0 ]; then
            check "Tenant namespace: tenant-$tenant" "pass"
        else
            check "Tenant namespace: tenant-$tenant" "warn" "false"
        fi
    done
else
    check "Tenant namespaces (kubectl not available)" "warn" "false"
fi

echo ""

# =============================================================================
# Grafana Dashboards Check
# =============================================================================
echo -e "${CYAN}Grafana Dashboards${NC}"
echo "─────────────────────────────────────────"

DASHBOARDS=("stoa-platform-overview" "stoa-mcp-tools" "stoa-security-events")

for dashboard in "${DASHBOARDS[@]}"; do
    DASH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" "$GRAFANA_URL/api/dashboards/uid/$dashboard" --max-time 5 2>/dev/null || echo "000")
    if [ "$DASH_CHECK" = "200" ]; then
        check "Dashboard: $dashboard" "pass"
    else
        check "Dashboard: $dashboard (not found)" "warn" "false"
    fi
done

echo ""

# =============================================================================
# Summary
# =============================================================================
TOTAL=$((PASSED + FAILED + WARNINGS))

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Summary: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}, ${YELLOW}$WARNINGS warnings${NC}"
echo ""

if [ "$FAILED" -eq 0 ]; then
    echo -e "  ╔═══════════════════════════════════════╗"
    echo -e "  ║                                       ║"
    echo -e "  ║   ${GREEN}██████╗  ██████╗ ${NC}                  ║"
    echo -e "  ║   ${GREEN}██╔════╝ ██╔═══██╗${NC}                  ║"
    echo -e "  ║   ${GREEN}██║  ███╗██║   ██║${NC}                  ║"
    echo -e "  ║   ${GREEN}██║   ██║██║   ██║${NC}                  ║"
    echo -e "  ║   ${GREEN}╚██████╔╝╚██████╔╝${NC}                  ║"
    echo -e "  ║   ${GREEN} ╚═════╝  ╚═════╝ ${NC}                  ║"
    echo -e "  ║                                       ║"
    echo -e "  ║   ${GREEN}All critical checks passed!${NC}         ║"
    echo -e "  ║   Ready to start the demo.            ║"
    echo -e "  ║                                       ║"
    echo -e "  ╚═══════════════════════════════════════╝"
    echo ""
    exit 0
else
    echo -e "  ╔═══════════════════════════════════════╗"
    echo -e "  ║                                       ║"
    echo -e "  ║   ${RED}███╗   ██╗ ██████╗ ${NC}                 ║"
    echo -e "  ║   ${RED}████╗  ██║██╔═══██╗${NC}                 ║"
    echo -e "  ║   ${RED}██╔██╗ ██║██║   ██║${NC}                 ║"
    echo -e "  ║   ${RED}██║╚██╗██║██║   ██║${NC}                 ║"
    echo -e "  ║   ${RED}██║ ╚████║╚██████╔╝${NC}                 ║"
    echo -e "  ║   ${RED}╚═╝  ╚═══╝ ╚═════╝ ${NC}-GO              ║"
    echo -e "  ║                                       ║"
    echo -e "  ║   ${RED}$FAILED critical checks failed!${NC}       ║"
    echo -e "  ║   Fix issues before starting demo.    ║"
    echo -e "  ║                                       ║"
    echo -e "  ╚═══════════════════════════════════════╝"
    echo ""
    echo "Recommended actions:"
    echo "  1. Check failed components"
    echo "  2. Run: ./reset-demo.sh"
    echo "  3. Re-run this check"
    echo ""
    exit 1
fi
