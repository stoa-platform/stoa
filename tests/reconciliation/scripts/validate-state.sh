#!/bin/bash
# validate-state.sh
# Quick validation script to check Git vs Gateway state alignment
#
# Usage:
#   ./validate-state.sh

set -euo pipefail

# Configuration
WM_GATEWAY_URL="${WM_GATEWAY_URL:-http://localhost:9072}"
WM_ADMIN_USER="${WM_ADMIN_USER:-Administrator}"
WM_ADMIN_PASSWORD="${WM_ADMIN_PASSWORD:?WM_ADMIN_PASSWORD is required}"
GITOPS_DIR="${GITOPS_DIR:-/opt/stoa-gitops}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "════════════════════════════════════════════════════════"
echo "  webMethods GitOps State Validation"
echo "════════════════════════════════════════════════════════"
echo ""

# Get APIs from Gateway
echo "📡 Fetching APIs from Gateway..."
GATEWAY_APIS=$(curl -s \
    "${WM_GATEWAY_URL}/rest/apigateway/apis" \
    -u "${WM_ADMIN_USER}:${WM_ADMIN_PASSWORD}" \
    -H "Accept: application/json" \
    | jq -r '.apiResponse[].apiName // empty' | sort)

GATEWAY_COUNT=$(echo "$GATEWAY_APIS" | grep -c . || echo 0)
echo "   Found: $GATEWAY_COUNT APIs"

# Get APIs from Git
echo "📁 Fetching APIs from Git..."
GIT_APIS=$(find "${GITOPS_DIR}/webmethods/apis" -name "*.yaml" 2>/dev/null \
    | xargs -I {} basename {} .yaml | sort)

GIT_COUNT=$(echo "$GIT_APIS" | grep -c . || echo 0)
echo "   Found: $GIT_COUNT APIs"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Comparison Results"
echo "════════════════════════════════════════════════════════"
echo ""

# Calculate differences
MISSING_FROM_GATEWAY=$(comm -23 <(echo "$GIT_APIS") <(echo "$GATEWAY_APIS") | grep . || true)
ORPHANS_ON_GATEWAY=$(comm -13 <(echo "$GIT_APIS") <(echo "$GATEWAY_APIS") | grep . || true)
IN_SYNC=$(comm -12 <(echo "$GIT_APIS") <(echo "$GATEWAY_APIS") | grep . || true)

SYNC_COUNT=$(echo "$IN_SYNC" | grep -c . || echo 0)
MISSING_COUNT=$(echo "$MISSING_FROM_GATEWAY" | grep -c . || echo 0)
ORPHAN_COUNT=$(echo "$ORPHANS_ON_GATEWAY" | grep -c . || echo 0)

# Display results
echo -e "${GREEN}✅ In Sync ($SYNC_COUNT):${NC}"
if [ -n "$IN_SYNC" ]; then
    echo "$IN_SYNC" | sed 's/^/   /'
else
    echo "   (none)"
fi
echo ""

if [ -n "$MISSING_FROM_GATEWAY" ]; then
    echo -e "${RED}❌ Missing from Gateway ($MISSING_COUNT):${NC}"
    echo "$MISSING_FROM_GATEWAY" | sed 's/^/   /'
    echo ""
fi

if [ -n "$ORPHANS_ON_GATEWAY" ]; then
    echo -e "${YELLOW}⚠️  Orphans on Gateway ($ORPHAN_COUNT):${NC}"
    echo "$ORPHANS_ON_GATEWAY" | sed 's/^/   /'
    echo ""
fi

echo "════════════════════════════════════════════════════════"
echo "  Summary"
echo "════════════════════════════════════════════════════════"
echo ""
echo "   Git APIs:      $GIT_COUNT"
echo "   Gateway APIs:  $GATEWAY_COUNT"
echo "   In Sync:       $SYNC_COUNT"
echo "   Missing:       $MISSING_COUNT"
echo "   Orphans:       $ORPHAN_COUNT"
echo ""

# Calculate drift percentage
if [ "$GIT_COUNT" -gt 0 ]; then
    DRIFT_PCT=$(( (MISSING_COUNT + ORPHAN_COUNT) * 100 / GIT_COUNT ))
else
    DRIFT_PCT=0
fi

if [ "$MISSING_COUNT" -eq 0 ] && [ "$ORPHAN_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✅ ALIGNED: Git and Gateway are in sync!${NC}"
    echo "   Drift: 0%"
    exit 0
else
    echo -e "${RED}❌ DRIFT DETECTED: Git and Gateway are NOT in sync${NC}"
    echo "   Drift: ${DRIFT_PCT}%"
    echo ""
    echo "   Run reconciliation to fix:"
    echo "   ansible-playbook reconcile-webmethods.yml -e env=\$ENV"
    exit 1
fi
