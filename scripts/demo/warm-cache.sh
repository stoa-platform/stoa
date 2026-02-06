#!/bin/bash
# =============================================================================
# CAB-1104: Semantic Cache Warming Script
# =============================================================================
# Pre-populates the semantic cache with common queries to demonstrate
# cache hit behavior during the demo.
#
# Creates 10 cache entries for:
# - CoinGecko price queries (BTC, ETH, SOL)
# - Weather forecasts (Paris, London, NYC)
# - Platform catalog queries
# - ML sentiment queries
#
# Usage: ./warm-cache.sh [--verbose]
# =============================================================================

set -e

# Configuration
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
VERBOSE="${1:-}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}STOA Semantic Cache Warming${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Counter
CACHED=0
FAILED=0

# Function to invoke tool and cache result
warm_tool() {
    local tool_name="$1"
    local arguments="$2"
    local tenant_id="${3:-high-five}"
    local description="$4"

    if [ "$VERBOSE" = "--verbose" ]; then
        echo -e "  ${YELLOW}Caching: $description${NC}"
    fi

    result=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/$tool_name/invoke" \
        -H "Content-Type: application/json" \
        -H "X-Tenant-ID: $tenant_id" \
        -d "{\"arguments\": $arguments}" \
        --max-time 10 \
        2>/dev/null || echo '{"error": "timeout"}')

    if echo "$result" | grep -q '"error"'; then
        ((FAILED++))
        if [ "$VERBOSE" = "--verbose" ]; then
            echo -e "    ${YELLOW}Failed (will retry on next run)${NC}"
        fi
    else
        ((CACHED++))
        if [ "$VERBOSE" = "--verbose" ]; then
            echo -e "    ${GREEN}Cached successfully${NC}"
        fi
    fi
}

echo -e "${YELLOW}Warming cache with 10 common queries...${NC}"
echo ""

# =============================================================================
# 1. CoinGecko Price Queries (high-five tenant)
# =============================================================================
echo -e "${BLUE}[1/4] Crypto prices (CoinGecko)${NC}"

warm_tool "high-five__crypto__get_prices" \
    '{"coins": ["bitcoin"], "currency": "usd"}' \
    "high-five" \
    "Bitcoin price (USD)"

warm_tool "high-five__crypto__get_prices" \
    '{"coins": ["ethereum"], "currency": "usd"}' \
    "high-five" \
    "Ethereum price (USD)"

warm_tool "high-five__crypto__get_prices" \
    '{"coins": ["bitcoin", "ethereum", "solana"], "currency": "eur"}' \
    "high-five" \
    "BTC/ETH/SOL prices (EUR)"

# =============================================================================
# 2. Weather Forecasts (high-five tenant)
# =============================================================================
echo -e "${BLUE}[2/4] Weather forecasts (Open-Meteo)${NC}"

warm_tool "high-five__weather__forecast" \
    '{"latitude": 48.8566, "longitude": 2.3522}' \
    "high-five" \
    "Paris weather"

warm_tool "high-five__weather__forecast" \
    '{"latitude": 51.5074, "longitude": -0.1278}' \
    "high-five" \
    "London weather"

warm_tool "high-five__weather__forecast" \
    '{"latitude": 40.7128, "longitude": -74.0060}' \
    "high-five" \
    "New York weather"

# =============================================================================
# 3. Platform Catalog (all tenants)
# =============================================================================
echo -e "${BLUE}[3/4] Platform catalog${NC}"

warm_tool "stoa_catalog_list" \
    '{}' \
    "high-five" \
    "API catalog (high-five)"

warm_tool "stoa_catalog_list" \
    '{}' \
    "ioi" \
    "API catalog (ioi)"

# =============================================================================
# 4. ML Sentiment (oasis tenant)
# =============================================================================
echo -e "${BLUE}[4/4] ML sentiment analysis${NC}"

warm_tool "stoa_ml_sentiment" \
    '{"inputs": "I love this product! Great quality!"}' \
    "oasis" \
    "Positive sentiment"

warm_tool "stoa_ml_sentiment" \
    '{"inputs": "Terrible service, very disappointed."}' \
    "oasis" \
    "Negative sentiment"

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Cache Warming Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Cached entries: ${GREEN}$CACHED${NC}"
echo -e "Failed entries: ${YELLOW}$FAILED${NC}"
echo ""

if [ $CACHED -ge 8 ]; then
    echo -e "Status: ${GREEN}Cache ready for demo${NC}"
else
    echo -e "Status: ${YELLOW}Partial cache - some APIs may be unavailable${NC}"
fi

echo ""
echo "The first call to each query will now be instant (< 5ms)"
echo "instead of making an external API call (100-500ms)."
echo ""
