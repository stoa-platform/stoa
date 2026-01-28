#!/bin/bash
# ============================================
# STOA Platform - Demo Warm-up Script
# Run 5 minutes before demo
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

NAMESPACE="stoa-system"

echo "🔥 STOA Platform Warm-up"
echo "========================"
echo ""

# Health checks
echo "1️⃣  Infrastructure Health Checks"
echo "─────────────────────────────────"

check_component() {
  local name=$1
  local cmd=$2
  printf "   %-20s" "$name"
  if eval "$cmd" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ UP${NC}"
    return 0
  else
    echo -e "${RED}❌ DOWN${NC}"
    return 1
  fi
}

FAILURES=0

check_component "PostgreSQL" "kubectl exec -n $NAMESPACE control-plane-db-0 -- pg_isready -q" || ((FAILURES++))
check_component "MCP Gateway" "kubectl exec -n $NAMESPACE deploy/mcp-gateway -- curl -sf http://localhost:8080/health" || ((FAILURES++))
check_component "webMethods" "kubectl exec -n $NAMESPACE deploy/apigateway -- curl -sf http://localhost:5555/health" || ((FAILURES++))
check_component "Keycloak" "kubectl exec -n $NAMESPACE deploy/keycloak -- curl -sf http://localhost:8080/health/ready" || ((FAILURES++))
check_component "Control Plane API" "kubectl exec -n $NAMESPACE deploy/control-plane-api -- curl -sf http://localhost:8000/health" || ((FAILURES++))
check_component "Redpanda (Kafka)" "kubectl exec -n $NAMESPACE redpanda-0 -- rpk cluster health" || ((FAILURES++))

echo ""

if [ $FAILURES -gt 0 ]; then
  echo -e "${RED}⚠️  $FAILURES component(s) unhealthy - check before demo!${NC}"
  exit 1
fi

# Warm-up calls
echo "2️⃣  Warming up services (3 rounds)"
echo "───────────────────────────────────"

for i in {1..3}; do
  printf "   Round $i/3..."

  # MCP Gateway - list tools
  kubectl exec -n $NAMESPACE deploy/mcp-gateway -- curl -sf http://localhost:8080/tools/list > /dev/null 2>&1

  # Control Plane API - list APIs
  kubectl exec -n $NAMESPACE deploy/control-plane-api -- curl -sf http://localhost:8000/api/v1/apis > /dev/null 2>&1

  # Keycloak - token endpoint warm-up
  kubectl exec -n $NAMESPACE deploy/keycloak -- curl -sf http://localhost:8080/realms/stoa/.well-known/openid-configuration > /dev/null 2>&1

  echo -e " ${GREEN}done${NC}"
  sleep 2
done

echo ""

# MCP Tools verification
echo "3️⃣  MCP Tools Verification"
echo "──────────────────────────"

TOOLS_COUNT=$(kubectl exec -n $NAMESPACE deploy/mcp-gateway -- curl -sf http://localhost:8080/tools/list 2>/dev/null | jq '.tools | length' 2>/dev/null || echo "0")
printf "   Available MCP tools: "
if [ "$TOOLS_COUNT" -gt 0 ]; then
  echo -e "${GREEN}$TOOLS_COUNT tools${NC}"
else
  echo -e "${YELLOW}Unable to count (jq not available or endpoint issue)${NC}"
fi

echo ""
echo "════════════════════════════════════"
echo -e "${GREEN}✅ STOA Platform ready for demo!${NC}"
echo "════════════════════════════════════"
echo ""
echo "Demo endpoints:"
echo "   • Portal:    https://portal.gostoa.dev"
echo "   • API:       https://api.gostoa.dev"
echo "   • MCP:       https://mcp.gostoa.dev"
echo ""
