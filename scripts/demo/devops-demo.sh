#!/bin/bash
# =============================================================================
# CAB-1104: DevOps Workflow Demo Script (Scenario 4)
# =============================================================================
# Demonstrates the "DevOps Workflow" scenario:
# 1. List GitHub issues using MCP tool
# 2. Create a pull request
# 3. Send Slack notification
#
# Uses mock endpoints by default for demo reliability.
# Set DEVOPS_TOOLS_MOCK=false to use real APIs with valid tokens.
# =============================================================================

set -e

# Configuration
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
TENANT_ID="${TENANT_ID:-oasis}"
GITHUB_OWNER="${GITHUB_OWNER:-stoa-platform}"
GITHUB_REPO="${GITHUB_REPO:-stoa}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CAB-1104: DevOps Workflow Demo${NC}"
echo -e "${BLUE}Scenario 4: GitHub + Slack Integration${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# =============================================================================
# Step 1: List GitHub Issues
# =============================================================================
echo -e "${YELLOW}Step 1: Listing GitHub issues...${NC}"
echo -e "${CYAN}Tool: stoa_devops_github_issues${NC}"
echo ""

ISSUES_RESPONSE=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_devops_github_issues/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"owner\": \"$GITHUB_OWNER\",
            \"repo\": \"$GITHUB_REPO\",
            \"state\": \"open\",
            \"per_page\": 5
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$ISSUES_RESPONSE" | jq '.' 2>/dev/null || echo "$ISSUES_RESPONSE"

if echo "$ISSUES_RESPONSE" | jq -e '.content[0].text' > /dev/null 2>&1; then
    RESULT=$(echo "$ISSUES_RESPONSE" | jq -r '.content[0].text' | jq '.')
    ISSUE_COUNT=$(echo "$RESULT" | jq '.total_count // 0')
    IS_MOCK=$(echo "$RESULT" | jq '.mock // false')

    echo ""
    echo -e "${GREEN}Found $ISSUE_COUNT open issues${NC}"
    if [ "$IS_MOCK" = "true" ]; then
        echo -e "${YELLOW}(Mock mode - for demo purposes)${NC}"
    fi
else
    echo -e "${YELLOW}Note: Direct API call - for demo, using mock data${NC}"
fi
echo ""

# =============================================================================
# Step 2: Create Pull Request
# =============================================================================
echo -e "${YELLOW}Step 2: Creating a pull request...${NC}"
echo -e "${CYAN}Tool: stoa_devops_github_pr${NC}"
echo ""

PR_RESPONSE=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_devops_github_pr/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"owner\": \"$GITHUB_OWNER\",
            \"repo\": \"$GITHUB_REPO\",
            \"title\": \"[Demo] Add automated workflow improvements\",
            \"body\": \"## Summary\\n- Automated via STOA MCP Gateway\\n- DevOps workflow demo\\n\\n## Test Plan\\n- Verify CI passes\\n- Review code changes\",
            \"head\": \"feature/demo-workflow\",
            \"base\": \"main\",
            \"draft\": true
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$PR_RESPONSE" | jq '.' 2>/dev/null || echo "$PR_RESPONSE"

if echo "$PR_RESPONSE" | jq -e '.content[0].text' > /dev/null 2>&1; then
    RESULT=$(echo "$PR_RESPONSE" | jq -r '.content[0].text' | jq '.')
    PR_NUMBER=$(echo "$RESULT" | jq '.pull_request.number // "N/A"')
    PR_URL=$(echo "$RESULT" | jq -r '.pull_request.html_url // "N/A"')

    echo ""
    echo -e "${GREEN}Created PR #$PR_NUMBER${NC}"
    echo -e "${CYAN}URL: $PR_URL${NC}"
else
    echo -e "${YELLOW}Note: Direct API call - for demo, using mock data${NC}"
fi
echo ""

# =============================================================================
# Step 3: Send Slack Notification
# =============================================================================
echo -e "${YELLOW}Step 3: Sending Slack notification...${NC}"
echo -e "${CYAN}Tool: stoa_devops_slack_notify${NC}"
echo ""

SLACK_RESPONSE=$(curl -s -X POST "$GATEWAY_URL/mcp/v1/tools/stoa_devops_slack_notify/invoke" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -d "{
        \"arguments\": {
            \"channel\": \"#devops\",
            \"message\": \":rocket: *DevOps Workflow Complete*\\n\\nPR created and issues tracked via STOA MCP Gateway.\\n\\n- Issues reviewed: 5\\n- PR created: #456\\n- Status: Ready for review\",
            \"username\": \"STOA Bot\",
            \"icon_emoji\": \":robot_face:\",
            \"attachments\": [
                {
                    \"color\": \"good\",
                    \"title\": \"Workflow Summary\",
                    \"text\": \"All DevOps tasks completed successfully\"
                }
            ]
        }
    }" 2>/dev/null || echo '{"error": "Connection failed"}')

echo "$SLACK_RESPONSE" | jq '.' 2>/dev/null || echo "$SLACK_RESPONSE"

if echo "$SLACK_RESPONSE" | jq -e '.content[0].text' > /dev/null 2>&1; then
    RESULT=$(echo "$SLACK_RESPONSE" | jq -r '.content[0].text' | jq '.')
    CHANNEL=$(echo "$RESULT" | jq -r '.notification.channel // "#devops"')

    echo ""
    echo -e "${GREEN}Notification sent to $CHANNEL${NC}"
else
    echo -e "${YELLOW}Note: Direct API call - for demo, using mock data${NC}"
fi
echo ""

# =============================================================================
# Summary
# =============================================================================
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}DevOps Workflow Demo Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "What we demonstrated:"
echo "  1. Listed GitHub issues via MCP tool"
echo "  2. Created a pull request programmatically"
echo "  3. Sent Slack notification with rich formatting"
echo ""
echo "Key STOA features shown:"
echo "  - External API bridging (GitHub, Slack)"
echo "  - MCP tool invocation"
echo "  - Multi-tenant support (X-Tenant-ID header)"
echo "  - Structured responses for AI agents"
echo ""
echo -e "${GREEN}DevOps automation with AI-native API management!${NC}"
echo ""
