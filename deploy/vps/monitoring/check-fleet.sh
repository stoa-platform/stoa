#!/usr/bin/env bash
# Quick health check: verify all VPS are pushing metrics to Pushgateway
#
# Usage: ./deploy/vps/monitoring/check-fleet.sh
set -euo pipefail

PUSHGATEWAY_URL="https://pushgateway.gostoa.dev"
PUSHGATEWAY_AUTH="arena:arena-push-2026"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "VPS Fleet Health Check"
echo "======================"
echo ""

# Expected instances
EXPECTED=(
  contabo-runner-github
  contabo-infisical
  contabo-hegemon-w1
  contabo-hegemon-w2
  contabo-hegemon-w3
  contabo-hegemon-w4
  contabo-hegemon-w5
  ovh-stoa-gateway
  ovh-kong
  ovh-agentgateway
  ovh-gravitee
  ovh-bench
  ovh-n8n-tooling
  ovh-vault
)

# Fetch all push timestamps from Pushgateway
METRICS=$(curl -sf -u "$PUSHGATEWAY_AUTH" "${PUSHGATEWAY_URL}/api/v1/metrics" 2>/dev/null) || {
  echo -e "${RED}ERROR: Cannot reach Pushgateway${NC}"
  exit 1
}

UP=0
DOWN=0
STALE=0
NOW=$(date +%s)

for instance in "${EXPECTED[@]}"; do
  # Check if this instance has pushed recently (within last 5 minutes)
  LAST_PUSH=$(echo "$METRICS" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for family in data.get('data', []):
    for sample in family.get('samples', []):
        labels = sample.get('labels', {})
        if labels.get('instance') == '$instance' and labels.get('job') == 'node_exporter':
            ts = sample.get('timestamp', 0)
            if ts:
                print(int(ts))
                sys.exit(0)
# Fallback: check push_time_seconds metric
for family in data.get('data', []):
    if 'push_time_seconds' in family.get('name', ''):
        for sample in family.get('samples', []):
            if sample.get('labels', {}).get('instance') == '$instance':
                print(int(float(sample.get('value', 0))))
                sys.exit(0)
print(0)
" 2>/dev/null || echo "0")

  if [[ "$LAST_PUSH" == "0" ]]; then
    echo -e "  ${RED}DOWN${NC}  $instance — no metrics found"
    ((DOWN++))
  else
    AGE=$((NOW - LAST_PUSH))
    if [[ $AGE -gt 300 ]]; then
      echo -e "  ${YELLOW}STALE${NC} $instance — last push ${AGE}s ago (>5min)"
      ((STALE++))
    else
      echo -e "  ${GREEN}UP${NC}    $instance — last push ${AGE}s ago"
      ((UP++))
    fi
  fi
done

echo ""
echo "========================================"
echo -e "  ${GREEN}UP${NC}: $UP   ${YELLOW}STALE${NC}: $STALE   ${RED}DOWN${NC}: $DOWN   Total: ${#EXPECTED[@]}"
echo "========================================"

[[ $DOWN -eq 0 && $STALE -eq 0 ]] && exit 0 || exit 1
