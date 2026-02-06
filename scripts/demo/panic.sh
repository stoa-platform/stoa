#!/bin/bash
# =============================================================================
# CAB-1104: Demo Panic Button - Offline Mode
# =============================================================================
# Emergency switch to offline mode when everything fails during the demo.
# This script:
# - Stops external API calls
# - Enables cache-only responses
# - Loads pre-recorded mock data
# - Provides a stable fallback experience
#
# Usage: ./panic.sh [--restore]
# =============================================================================

set -e

# Configuration
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOCK_DATA_DIR="$SCRIPT_DIR/mock-data"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check for restore mode
if [ "$1" = "--restore" ]; then
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Restoring Normal Mode${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    # Restore normal mode
    if command -v kubectl &> /dev/null; then
        echo -e "${YELLOW}Removing offline mode ConfigMap...${NC}"
        kubectl delete configmap stoa-demo-offline-mode -n stoa-system 2>/dev/null || true

        echo -e "${YELLOW}Restarting MCP Gateway...${NC}"
        kubectl rollout restart deployment/mcp-gateway -n stoa-system

        echo -e "${YELLOW}Waiting for rollout...${NC}"
        kubectl rollout status deployment/mcp-gateway -n stoa-system --timeout=60s
    fi

    echo ""
    echo -e "${GREEN}Normal mode restored!${NC}"
    echo "External API calls are now enabled."
    exit 0
fi

echo -e "${RED}========================================${NC}"
echo -e "${RED}   PANIC BUTTON - OFFLINE MODE${NC}"
echo -e "${RED}========================================${NC}"
echo ""
echo -e "${YELLOW}This will switch STOA to offline mode:${NC}"
echo "  - All external API calls will be blocked"
echo "  - Responses will come from local cache/mock data"
echo "  - Dashboard will show static/cached metrics"
echo ""

# Confirmation
read -p "Are you sure? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo -e "${YELLOW}Activating offline mode...${NC}"

# =============================================================================
# Step 1: Create mock data directory if needed
# =============================================================================
echo -e "${BLUE}[1/4] Preparing mock data...${NC}"

mkdir -p "$MOCK_DATA_DIR"

# Create mock responses if they don't exist
if [ ! -f "$MOCK_DATA_DIR/coingecko-prices.json" ]; then
    cat > "$MOCK_DATA_DIR/coingecko-prices.json" << 'EOF'
{
  "bitcoin": {"usd": 65432.00, "eur": 60123.00},
  "ethereum": {"usd": 3456.78, "eur": 3187.00},
  "solana": {"usd": 142.50, "eur": 131.25}
}
EOF
fi

if [ ! -f "$MOCK_DATA_DIR/weather-paris.json" ]; then
    cat > "$MOCK_DATA_DIR/weather-paris.json" << 'EOF'
{
  "latitude": 48.8566,
  "longitude": 2.3522,
  "current_weather": {
    "temperature": 12.5,
    "windspeed": 15.2,
    "weathercode": 3,
    "time": "2024-02-06T14:00"
  }
}
EOF
fi

if [ ! -f "$MOCK_DATA_DIR/sentiment-positive.json" ]; then
    cat > "$MOCK_DATA_DIR/sentiment-positive.json" << 'EOF'
{
  "success": true,
  "mock": true,
  "prediction": {
    "label": "POSITIVE",
    "confidence": 0.92
  },
  "result": [
    {"label": "POSITIVE", "score": 0.92},
    {"label": "NEGATIVE", "score": 0.08}
  ]
}
EOF
fi

echo -e "${GREEN}  Mock data prepared${NC}"

# =============================================================================
# Step 2: Apply offline mode ConfigMap
# =============================================================================
echo -e "${BLUE}[2/4] Applying offline mode configuration...${NC}"

if command -v kubectl &> /dev/null; then
    # Create ConfigMap for offline mode
    kubectl apply -f - << 'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: stoa-demo-offline-mode
  namespace: stoa-system
data:
  STOA_DEMO_MODE: "offline"
  STOA_CACHE_ONLY: "true"
  STOA_EXTERNAL_APIS_ENABLED: "false"
  DEVOPS_TOOLS_MOCK: "true"
  ML_TOOLS_MOCK: "true"
EOF
    echo -e "${GREEN}  ConfigMap applied${NC}"
else
    echo -e "${YELLOW}  kubectl not available, skipping K8s config${NC}"
fi

# =============================================================================
# Step 3: Set environment variable for local scripts
# =============================================================================
echo -e "${BLUE}[3/4] Setting environment variables...${NC}"

export STOA_DEMO_MODE=offline
export STOA_CACHE_ONLY=true
export DEVOPS_TOOLS_MOCK=true
export ML_TOOLS_MOCK=true

# Create env file for other scripts
cat > "$SCRIPT_DIR/.demo-offline-mode" << EOF
export STOA_DEMO_MODE=offline
export STOA_CACHE_ONLY=true
export DEVOPS_TOOLS_MOCK=true
export ML_TOOLS_MOCK=true
EOF

echo -e "${GREEN}  Environment variables set${NC}"

# =============================================================================
# Step 4: Restart gateway if possible
# =============================================================================
echo -e "${BLUE}[4/4] Restarting MCP Gateway...${NC}"

if command -v kubectl &> /dev/null; then
    kubectl rollout restart deployment/mcp-gateway -n stoa-system 2>/dev/null || true
    echo -e "${GREEN}  Gateway restart initiated${NC}"
else
    echo -e "${YELLOW}  Manual gateway restart may be needed${NC}"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${RED}========================================${NC}"
echo -e "${GREEN}OFFLINE MODE ACTIVATED${NC}"
echo -e "${RED}========================================${NC}"
echo ""
echo "What happens now:"
echo "  - All external API calls return mock data"
echo "  - Semantic cache serves pre-loaded responses"
echo "  - Dashboards show cached metrics"
echo "  - Demo continues with predictable data"
echo ""
echo "To restore normal mode:"
echo -e "  ${CYAN}./panic.sh --restore${NC}"
echo ""
echo -e "${YELLOW}Mock data location: $MOCK_DATA_DIR${NC}"
echo ""

# Keep the script "sourced" so env vars persist
echo "To apply env vars in your current shell:"
echo -e "  ${CYAN}source $SCRIPT_DIR/.demo-offline-mode${NC}"
echo ""
