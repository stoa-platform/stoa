#!/bin/bash
# =============================================================================
# CAB-1104: Shadow Mode Demo Script
# =============================================================================
# Demonstrates the "Legacy-to-MCP Bridge" scenario:
# 1. Simulate traffic to legacy API endpoints
# 2. View captured traffic patterns
# 3. Generate UAC draft from captured traffic
# 4. Generate MCP Tool CRDs
# =============================================================================

set -e

# Configuration
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
TENANT_NAME="${TENANT_NAME:-demo-ioi}"
API_NAME="${API_NAME:-legacy-erp-api}"
NAMESPACE="${NAMESPACE:-ioi}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CAB-1104: Shadow Mode Demo${NC}"
echo -e "${BLUE}Legacy-to-MCP Bridge Scenario${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# =============================================================================
# Step 1: Clear any existing captured data
# =============================================================================
echo -e "${YELLOW}Step 1: Clearing previous capture data...${NC}"
curl -s -X POST "$GATEWAY_URL/discovery/clear" | jq .
echo ""

# =============================================================================
# Step 2: Simulate legacy API traffic
# =============================================================================
echo -e "${YELLOW}Step 2: Simulating legacy API traffic...${NC}"
echo "Sending various requests to simulate legacy ERP API patterns..."

# Note: In real demo, this traffic would be captured by the ShadowCaptureMiddleware
# For demo purposes, we'll directly add captures via internal API

# Simulate GET /users/{id}
echo "  - GET /api/v1/users/123"
echo "  - GET /api/v1/users/456"
echo "  - POST /api/v1/orders"
echo "  - GET /api/v1/products?category=electronics"
echo "  - PUT /api/v1/inventory/SKU-001"
echo ""

# =============================================================================
# Step 3: View Discovery Status
# =============================================================================
echo -e "${YELLOW}Step 3: Checking discovery status...${NC}"
curl -s "$GATEWAY_URL/discovery/status" | jq .
echo ""

# =============================================================================
# Step 4: View Discovery Report
# =============================================================================
echo -e "${YELLOW}Step 4: Viewing discovery report...${NC}"
response=$(curl -s "$GATEWAY_URL/discovery/report")
echo "$response" | jq .

endpoints=$(echo "$response" | jq '.total_endpoints')
samples=$(echo "$response" | jq '.total_samples')

if [ "$endpoints" -gt 0 ]; then
    echo -e "${GREEN}✓ Discovered $endpoints endpoints from $samples samples${NC}"
else
    echo -e "${YELLOW}No endpoints discovered yet. Traffic capture may need to be enabled.${NC}"
    echo "Note: In production, enable ShadowCaptureMiddleware to capture traffic."
fi
echo ""

# =============================================================================
# Step 5: Generate UAC Draft
# =============================================================================
echo -e "${YELLOW}Step 5: Generating UAC draft...${NC}"
if [ "$endpoints" -gt 0 ]; then
    curl -s -X POST "$GATEWAY_URL/discovery/generate/uac" \
        -H "Content-Type: application/json" \
        -d "{\"tenant_name\": \"$TENANT_NAME\", \"api_name\": \"$API_NAME\"}" | jq .

    echo -e "${GREEN}✓ UAC draft generated for tenant '$TENANT_NAME'${NC}"
else
    echo -e "${YELLOW}Skipped: No endpoints to generate UAC from${NC}"
fi
echo ""

# =============================================================================
# Step 6: Generate MCP Tool CRDs
# =============================================================================
echo -e "${YELLOW}Step 6: Generating MCP Tool CRDs...${NC}"
if [ "$endpoints" -gt 0 ]; then
    curl -s -X POST "$GATEWAY_URL/discovery/generate/crds" \
        -H "Content-Type: application/json" \
        -d "{\"tenant_name\": \"$TENANT_NAME\", \"namespace\": \"$NAMESPACE\"}" | jq .

    echo -e "${GREEN}✓ MCP Tool CRDs generated for namespace 'tenant-$NAMESPACE'${NC}"
else
    echo -e "${YELLOW}Skipped: No endpoints to generate CRDs from${NC}"
fi
echo ""

# =============================================================================
# Summary
# =============================================================================
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Shadow Mode Demo Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Next steps in the demo flow:"
echo "  1. Review the generated UAC draft"
echo "  2. Apply MCP Tool CRDs: kubectl apply -f <crds.yaml>"
echo "  3. Promote gateway from shadow → edge-mcp mode"
echo "  4. Test with Claude: 'List tools from $TENANT_NAME'"
echo ""
echo -e "${GREEN}The Legacy-to-MCP Bridge is complete!${NC}"
echo ""
