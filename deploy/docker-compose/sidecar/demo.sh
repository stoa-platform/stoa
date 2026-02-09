#!/usr/bin/env bash
# =============================================================================
# STOA Sidecar Mode — Demo Script
# =============================================================================
# Starts the sidecar Docker Compose stack and runs through demo scenarios:
#   1. Request without token → 401 Unauthorized
#   2. Request with valid token → 200 OK (customers)
#   3. Request with valid token → 200 OK (orders)
#   4. POST with valid token → 201 Created
#   5. Direct /authz call (no user) → 401
#   6. Direct /authz call (with user) → 200
#   7. Gateway Prometheus metrics
#
# Usage:
#   cd deploy/docker-compose
#   ./sidecar/demo.sh
# =============================================================================

set -euo pipefail

# --- Colors ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Config ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="docker-compose.sidecar.yml"
PROXY_URL="http://localhost:${PORT_PROXY:-8080}"
GATEWAY_URL="http://localhost:${PORT_GATEWAY:-8081}"
DEMO_TOKEN="demo-token-valid"

passed=0
failed=0

# --- Helpers ---
banner() {
    echo ""
    echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

step() {
    echo -e "${CYAN}▸ $1${NC}"
}

check() {
    local description="$1"
    local expected="$2"
    local actual="$3"

    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}✓ PASS${NC} — $description (HTTP $actual)"
        ((passed++))
    else
        echo -e "  ${RED}✗ FAIL${NC} — $description (expected $expected, got $actual)"
        ((failed++))
    fi
}

wait_for_service() {
    local name="$1"
    local url="$2"
    local max_retries=30
    local i=0

    printf "  Waiting for %s..." "$name"
    while [ $i -lt $max_retries ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo -e " ${GREEN}ready${NC}"
            return 0
        fi
        printf "."
        sleep 2
        ((i++))
    done
    echo -e " ${RED}TIMEOUT${NC}"
    return 1
}

cleanup() {
    if [ "${KEEP_RUNNING:-}" != "true" ]; then
        banner "Cleanup"
        step "Stopping services..."
        cd "$COMPOSE_DIR"
        docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
    else
        echo ""
        echo -e "${YELLOW}Services still running. Stop with:${NC}"
        echo "  cd $COMPOSE_DIR && docker compose -f $COMPOSE_FILE down"
    fi
}

# =============================================================================
# Main
# =============================================================================

banner "STOA Gateway — Sidecar Mode Demo"

echo -e "${BOLD}Architecture:${NC}"
echo ""
echo "  Client Request"
echo "       │"
echo "       ▼"
echo "  ┌─────────────┐    auth_request     ┌─────────────────┐"
echo "  │ nginx-proxy  │ ─────────────────▸  │  stoa-gateway   │"
echo "  │  :8080       │                     │  :8081 (sidecar)│"
echo "  │              │  ◂── allow/deny ──  │  POST /authz    │"
echo "  │              │                     └─────────────────┘"
echo "  │              │    proxy_pass"
echo "  │              │ ─────────────────▸  ┌─────────────────┐"
echo "  │              │   (if allowed)      │ fake-webmethods │"
echo "  └─────────────┘                     │  :8080 (mock)   │"
echo "                                      └─────────────────┘"
echo ""

# --- Step 1: Start services ---
banner "Step 1: Start Services"

cd "$COMPOSE_DIR"
step "Building and starting containers..."
docker compose -f "$COMPOSE_FILE" up -d --build

step "Waiting for services to be healthy..."
wait_for_service "stoa-gateway" "$GATEWAY_URL/health"
wait_for_service "nginx-proxy" "$PROXY_URL/health"

echo ""
step "All services ready."

# --- Step 2: Test without token → 401 ---
banner "Step 2: Request Without Token"

step "GET $PROXY_URL/api/customers (no Authorization header)"
HTTP_CODE=$(curl -s -o /tmp/sidecar-response.json -w "%{http_code}" "$PROXY_URL/api/customers")
check "No token → 401 Unauthorized" "401" "$HTTP_CODE"
echo -e "  ${YELLOW}Response:${NC}"
cat /tmp/sidecar-response.json | python3 -m json.tool 2>/dev/null || cat /tmp/sidecar-response.json
echo ""

# --- Step 3: Request with valid token → 200 (customers) ---
banner "Step 3: Authenticated Request — Customers"

step "GET $PROXY_URL/api/customers (Bearer $DEMO_TOKEN)"
HTTP_CODE=$(curl -s -o /tmp/sidecar-response.json -w "%{http_code}" \
    -H "Authorization: Bearer $DEMO_TOKEN" \
    "$PROXY_URL/api/customers")
check "Valid token → 200 OK (customers)" "200" "$HTTP_CODE"
echo -e "  ${YELLOW}Response:${NC}"
cat /tmp/sidecar-response.json | python3 -m json.tool 2>/dev/null || cat /tmp/sidecar-response.json
echo ""

# --- Step 4: Request with valid token → 200 (orders) ---
banner "Step 4: Authenticated Request — Orders"

step "GET $PROXY_URL/api/orders (Bearer $DEMO_TOKEN)"
HTTP_CODE=$(curl -s -o /tmp/sidecar-response.json -w "%{http_code}" \
    -H "Authorization: Bearer $DEMO_TOKEN" \
    "$PROXY_URL/api/orders")
check "Valid token → 200 OK (orders)" "200" "$HTTP_CODE"
echo -e "  ${YELLOW}Response (truncated):${NC}"
cat /tmp/sidecar-response.json | python3 -m json.tool 2>/dev/null | head -20 || cat /tmp/sidecar-response.json | head -20
echo "  ..."
echo ""

# --- Step 5: POST with valid token → 201 ---
banner "Step 5: Create Order (POST)"

step "POST $PROXY_URL/api/orders (Bearer $DEMO_TOKEN)"
HTTP_CODE=$(curl -s -o /tmp/sidecar-response.json -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $DEMO_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"customer_id":"cust-001","items":[{"product":"API License","quantity":1}]}' \
    "$PROXY_URL/api/orders")
check "POST with token → 201 Created" "201" "$HTTP_CODE"
echo -e "  ${YELLOW}Response:${NC}"
cat /tmp/sidecar-response.json | python3 -m json.tool 2>/dev/null || cat /tmp/sidecar-response.json
echo ""

# --- Step 6: Direct /authz — no user → 401 ---
banner "Step 6: Direct Gateway /authz — No User"

step "POST $GATEWAY_URL/authz (no user in body)"
HTTP_CODE=$(curl -s -o /tmp/sidecar-response.json -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"method":"GET","path":"/api/customers","headers":{}}' \
    "$GATEWAY_URL/authz")
check "authz without user → 401" "401" "$HTTP_CODE"
echo ""

# --- Step 7: Direct /authz — with user → 200 ---
banner "Step 7: Direct Gateway /authz — With User"

step "POST $GATEWAY_URL/authz (user + tenant in body)"
HTTP_CODE=$(curl -s -o /tmp/sidecar-response.json -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{
      "method": "GET",
      "path": "/api/customers",
      "headers": {"Authorization": "Bearer demo-token"},
      "tenant_id": "demo-tenant",
      "user": {
        "id": "demo-user",
        "email": "demo@stoa.dev",
        "roles": ["admin"],
        "scopes": ["read", "write"]
      }
    }' \
    "$GATEWAY_URL/authz")
check "authz with user → 200" "200" "$HTTP_CODE"
echo ""

# --- Step 8: Prometheus metrics ---
banner "Step 8: Gateway Metrics"

step "GET $GATEWAY_URL/metrics"
echo ""
METRICS=$(curl -s "$GATEWAY_URL/metrics")
if [ -n "$METRICS" ]; then
    echo -e "  ${GREEN}Metrics endpoint available${NC}"
    echo "$METRICS" | head -20
    TOTAL_LINES=$(echo "$METRICS" | wc -l)
    echo -e "  ... ($TOTAL_LINES total metric lines)"
else
    echo -e "  ${YELLOW}No metrics available yet${NC}"
fi
echo ""

# --- Summary ---
banner "Results"

TOTAL=$((passed + failed))
echo -e "  ${GREEN}Passed: $passed${NC}"
echo -e "  ${RED}Failed: $failed${NC}"
echo -e "  ${BOLD}Total:  $TOTAL${NC}"
echo ""

if [ "$failed" -gt 0 ]; then
    echo -e "  ${RED}Some tests failed. Check the gateway logs:${NC}"
    echo "    docker compose -f $COMPOSE_FILE logs stoa-gateway"
    echo ""
fi

echo -e "  ${BOLD}Useful commands:${NC}"
echo "    docker compose -f $COMPOSE_FILE logs -f stoa-gateway  # Gateway logs"
echo "    docker compose -f $COMPOSE_FILE logs -f nginx-proxy   # Proxy logs"
echo "    curl $GATEWAY_URL/health                              # Health check"
echo "    curl $GATEWAY_URL/metrics                             # Prometheus metrics"
echo ""

# --- Cleanup ---
cleanup

rm -f /tmp/sidecar-response.json

exit $failed
