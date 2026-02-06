#!/bin/bash
# =============================================================================
# CAB-1104: AI Pipeline Bridge Demo Script (Scenario 5)
# =============================================================================
# Demonstrates the "AI Pipeline Bridge" scenario:
# 1. Sentiment analysis on customer reviews
# 2. Zero-shot text classification for support tickets
# 3. Token budget governance per tenant
#
# Uses mock HuggingFace responses by default.
# Set ML_TOOLS_MOCK=false and HUGGINGFACE_TOKEN to use real API.
# =============================================================================

set -e

# Configuration
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
TENANT_ID="${TENANT_ID:-oasis}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CAB-1104: AI Pipeline Bridge Demo${NC}"
echo -e "${BLUE}Scenario 5: ML Inference + Token Budget${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# =============================================================================
# Step 1: Check Token Budget
# =============================================================================
echo -e "${YELLOW}Step 1: Checking ML token budget for tenant '$TENANT_ID'...${NC}"
echo -e "${CYAN}Tool: stoa_ml_budget${NC}"
echo ""

BUDGET_RESPONSE=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_ml_budget/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"tenant_id\": \"$TENANT_ID\"
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$BUDGET_RESPONSE" | jq '.' 2>/dev/null || echo "$BUDGET_RESPONSE"
echo ""

# =============================================================================
# Step 2: Sentiment Analysis on Customer Reviews
# =============================================================================
echo -e "${YELLOW}Step 2: Analyzing sentiment of customer reviews...${NC}"
echo -e "${CYAN}Tool: stoa_ml_sentiment${NC}"
echo ""

# Positive review
echo -e "${MAGENTA}Review 1 (Positive):${NC}"
echo "\"I absolutely love this product! It exceeded all my expectations. Amazing quality!\""
echo ""

SENTIMENT_1=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_ml_sentiment/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"inputs\": \"I absolutely love this product! It exceeded all my expectations. Amazing quality!\"
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$SENTIMENT_1" | jq '.' 2>/dev/null || echo "$SENTIMENT_1"
echo ""

# Negative review
echo -e "${MAGENTA}Review 2 (Negative):${NC}"
echo "\"Terrible experience. The product broke after one day. Very disappointed with the poor quality.\""
echo ""

SENTIMENT_2=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_ml_sentiment/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"inputs\": \"Terrible experience. The product broke after one day. Very disappointed with the poor quality.\"
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$SENTIMENT_2" | jq '.' 2>/dev/null || echo "$SENTIMENT_2"
echo ""

# =============================================================================
# Step 3: Zero-Shot Classification for Support Tickets
# =============================================================================
echo -e "${YELLOW}Step 3: Classifying support tickets (zero-shot)...${NC}"
echo -e "${CYAN}Tool: stoa_ml_classify${NC}"
echo ""

# Technical issue
echo -e "${MAGENTA}Ticket 1: Technical Issue${NC}"
echo "\"The server keeps crashing when I try to upload large files. Error code 503.\""
echo ""

CLASSIFY_1=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_ml_classify/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"inputs\": \"The server keeps crashing when I try to upload large files. Error code 503.\",
            \"candidate_labels\": [\"bug\", \"feature request\", \"billing\", \"general question\"]
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$CLASSIFY_1" | jq '.' 2>/dev/null || echo "$CLASSIFY_1"
echo ""

# Feature request
echo -e "${MAGENTA}Ticket 2: Feature Request${NC}"
echo "\"It would be great if you could add dark mode to the application. Many users are asking for it.\""
echo ""

CLASSIFY_2=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_ml_classify/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"inputs\": \"It would be great if you could add dark mode to the application. Many users are asking for it.\",
            \"candidate_labels\": [\"bug\", \"feature request\", \"billing\", \"general question\"]
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$CLASSIFY_2" | jq '.' 2>/dev/null || echo "$CLASSIFY_2"
echo ""

# =============================================================================
# Step 4: Check Updated Token Budget
# =============================================================================
echo -e "${YELLOW}Step 4: Checking token budget after ML operations...${NC}"
echo -e "${CYAN}Tool: stoa_ml_budget${NC}"
echo ""

BUDGET_AFTER=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_ml_budget/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"tenant_id\": \"$TENANT_ID\"
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$BUDGET_AFTER" | jq '.' 2>/dev/null || echo "$BUDGET_AFTER"
echo ""

# =============================================================================
# Summary
# =============================================================================
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI Pipeline Bridge Demo Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "What we demonstrated:"
echo "  1. Token budget governance per tenant"
echo "  2. Sentiment analysis using DistilBERT"
echo "  3. Zero-shot classification using BART"
echo "  4. Cost tracking and usage monitoring"
echo ""
echo "Key STOA features shown:"
echo "  - ML model exposure as MCP tools"
echo "  - Per-tenant token budgets"
echo "  - Cost allocation and tracking"
echo "  - Governance for AI workloads"
echo ""
echo "Models used:"
echo "  - Sentiment: distilbert-base-uncased-finetuned-sst-2-english"
echo "  - Classification: facebook/bart-large-mnli"
echo ""
echo -e "${GREEN}AI-native API management with ML governance!${NC}"
echo ""
