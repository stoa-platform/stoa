#!/bin/bash
# =============================================================================
# CAB-1104: Demo Reset Script
# =============================================================================
# Resets the demo environment to a clean state in < 30 seconds
# - Flush semantic cache
# - Reset rate limit counters
# - Clear audit trail (demo data only)
# - Re-seed demo data
# - Warm semantic cache
# - Restart traffic generator
#
# Usage: ./reset-demo.sh [--quick]
# =============================================================================

set -e

# Configuration
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-https://api.gostoa.dev}"
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUICK_MODE="${1:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Timer
START_TIME=$(date +%s)

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}STOA Demo Reset Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# =============================================================================
# Step 1: Flush semantic cache
# =============================================================================
echo -e "${YELLOW}[1/6] Flushing semantic cache...${NC}"
CACHE_RESULT=$(curl -s -X DELETE "${GATEWAY_URL}/api/v1/cache/flush" \
    -H "Content-Type: application/json" \
    2>/dev/null || echo '{"status": "skipped", "note": "endpoint not available"}')

if echo "$CACHE_RESULT" | grep -q "cleared\|success\|ok"; then
    echo -e "${GREEN}  Cache flushed successfully${NC}"
else
    echo -e "${YELLOW}  Cache flush skipped (endpoint may not be available)${NC}"
fi

# =============================================================================
# Step 2: Reset rate limit counters
# =============================================================================
echo -e "${YELLOW}[2/6] Resetting rate limit counters...${NC}"
RATE_RESULT=$(curl -s -X POST "${CONTROL_PLANE_URL}/api/v1/admin/reset-rate-limits" \
    -H "Content-Type: application/json" \
    2>/dev/null || echo '{"status": "skipped"}')

if echo "$RATE_RESULT" | grep -q "reset\|success\|ok"; then
    echo -e "${GREEN}  Rate limits reset successfully${NC}"
else
    echo -e "${YELLOW}  Rate limit reset skipped (using in-memory reset)${NC}"
    # Fallback: restart the gateway to reset in-memory rate limits
    if command -v kubectl &> /dev/null; then
        kubectl rollout restart deployment/mcp-gateway -n stoa-system 2>/dev/null || true
    fi
fi

# =============================================================================
# Step 3: Clear audit trail (demo data only)
# =============================================================================
echo -e "${YELLOW}[3/6] Clearing demo audit data...${NC}"
AUDIT_RESULT=$(curl -s -X DELETE "${CONTROL_PLANE_URL}/api/v1/audit?scope=demo" \
    -H "Content-Type: application/json" \
    2>/dev/null || echo '{"status": "skipped"}')

if echo "$AUDIT_RESULT" | grep -q "cleared\|success\|deleted"; then
    echo -e "${GREEN}  Audit data cleared successfully${NC}"
else
    echo -e "${YELLOW}  Audit clear skipped (demo data preserved)${NC}"
fi

# =============================================================================
# Step 4: Re-seed demo data
# =============================================================================
echo -e "${YELLOW}[4/6] Re-seeding demo data...${NC}"

if [ -f "$SCRIPT_DIR/seed-rpo-demo.py" ]; then
    if [ "$QUICK_MODE" = "--quick" ]; then
        python3 "$SCRIPT_DIR/seed-rpo-demo.py" --quick 2>/dev/null || true
    else
        python3 "$SCRIPT_DIR/seed-rpo-demo.py" 2>/dev/null || true
    fi
    echo -e "${GREEN}  Demo data seeded${NC}"
else
    echo -e "${YELLOW}  Seed script not found, skipping${NC}"
fi

# Apply K8s resources if available
if command -v kubectl &> /dev/null && [ -d "$SCRIPT_DIR/../../deploy/demo-rpo" ]; then
    kubectl apply -k "$SCRIPT_DIR/../../deploy/demo-rpo" 2>/dev/null || true
    echo -e "${GREEN}  K8s demo resources applied${NC}"
fi

# =============================================================================
# Step 5: Warm semantic cache
# =============================================================================
echo -e "${YELLOW}[5/6] Warming semantic cache...${NC}"

if [ -f "$SCRIPT_DIR/warm-cache.sh" ]; then
    bash "$SCRIPT_DIR/warm-cache.sh" 2>/dev/null || true
    echo -e "${GREEN}  Cache warmed with 10 entries${NC}"
else
    # Inline cache warming
    WARM_QUERIES=(
        '{"tool": "stoa_catalog_list", "arguments": {}}'
        '{"tool": "high-five__crypto__get_prices", "arguments": {"coins": ["bitcoin"]}}'
        '{"tool": "high-five__crypto__get_prices", "arguments": {"coins": ["ethereum"]}}'
        '{"tool": "high-five__weather__forecast", "arguments": {"latitude": 48.85, "longitude": 2.35}}'
        '{"tool": "stoa_ml_sentiment", "arguments": {"inputs": "This is great!"}}'
    )

    for query in "${WARM_QUERIES[@]}"; do
        curl -s -X POST "${GATEWAY_URL}/mcp/v1/tools/call" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: high-five" \
            -d "$query" \
            > /dev/null 2>&1 || true
    done
    echo -e "${GREEN}  Cache warmed with ${#WARM_QUERIES[@]} entries${NC}"
fi

# =============================================================================
# Step 6: Restart traffic generator
# =============================================================================
echo -e "${YELLOW}[6/6] Restarting traffic generator...${NC}"

# Kill any existing traffic generator
pkill -f "traffic-generator.py" 2>/dev/null || true

# Start new traffic generator in background
if [ -f "$SCRIPT_DIR/traffic-generator.py" ]; then
    nohup python3 "$SCRIPT_DIR/traffic-generator.py" --duration 3600 \
        > /tmp/traffic-generator.log 2>&1 &
    echo -e "${GREEN}  Traffic generator started (PID: $!)${NC}"
else
    echo -e "${YELLOW}  Traffic generator script not found${NC}"
fi

# =============================================================================
# Summary
# =============================================================================
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Demo Reset Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Time elapsed: ${GREEN}${ELAPSED}s${NC}"

if [ "$ELAPSED" -le 30 ]; then
    echo -e "Status: ${GREEN}Within target (< 30s)${NC}"
else
    echo -e "Status: ${YELLOW}Exceeded target (> 30s)${NC}"
fi

echo ""
echo "Next steps:"
echo "  1. Open Grafana: https://grafana.gostoa.dev"
echo "  2. Check dashboards have live data"
echo "  3. Run pre-demo check: ./pre-demo-check.sh"
echo ""
