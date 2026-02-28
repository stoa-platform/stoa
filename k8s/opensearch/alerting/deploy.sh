#!/usr/bin/env bash
# OpenSearch Alerting Bootstrap — Deploy monitors + notification channel
# Usage: KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/opensearch/alerting/deploy.sh
#
# Prerequisites:
#   - OpenSearch running with alerting plugin
#   - SLACK_WEBHOOK_URL env var (or pass as arg: ./deploy.sh <webhook_url>)
#   - OPENSEARCH_PASSWORD env var (or uses Infisical)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_POD="opensearch-0"
OS_NS="opensearch"
OS_USER="admin"
OS_PASS="${OPENSEARCH_PASSWORD:-}"
SLACK_URL="${1:-${SLACK_WEBHOOK_URL:-}}"

# --- Resolve OpenSearch password from Infisical if not set ---
if [ -z "$OS_PASS" ]; then
  echo "OPENSEARCH_PASSWORD not set, fetching from Infisical..."
  eval "$(infisical-token)"
  OS_PASS=$(infisical secrets get ADMIN_PASSWORD --env=prod --path=/opensearch \
    --projectId="97972ffc-990b-4d28-9c4d-0664d217f03b" \
    --domain=https://vault.gostoa.dev/api --plain 2>/dev/null || true)
  if [ -z "$OS_PASS" ]; then
    echo "ERROR: could not retrieve OpenSearch password from Infisical"
    exit 1
  fi
fi

if [ -z "$SLACK_URL" ]; then
  echo "ERROR: SLACK_WEBHOOK_URL env var or argument required"
  echo "Usage: SLACK_WEBHOOK_URL=https://hooks.slack.com/... $0"
  exit 1
fi

os_curl() {
  kubectl exec -n "$OS_NS" "$OS_POD" -c opensearch -- \
    curl -s -u "${OS_USER}:${OS_PASS}" -H 'Content-Type: application/json' "$@"
}

TOTAL=4
echo "=== OpenSearch Alerting Bootstrap ==="
echo ""

# 1. Create Slack notification channel (notifications plugin API for 2.x)
echo "[1/$TOTAL] Creating Slack notification channel..."

# Check if channel already exists
EXISTING=$(os_curl -X GET 'http://localhost:9200/_plugins/_notifications/configs' 2>/dev/null || true)
DEST_ID=$(echo "$EXISTING" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data.get('config_list', []):
    if item.get('config', {}).get('name') == 'STOA Slack Alerts':
        print(item['config_id'])
        break
" 2>/dev/null || true)

if [ -n "$DEST_ID" ]; then
  echo "  Channel already exists: $DEST_ID"
  # Update webhook URL in case it changed
  os_curl -X PUT "http://localhost:9200/_plugins/_notifications/configs/$DEST_ID" \
    -d "{
      \"config_id\": \"$DEST_ID\",
      \"config\": {
        \"name\": \"STOA Slack Alerts\",
        \"description\": \"OpenSearch alerting → Slack #stoa-alerts\",
        \"config_type\": \"slack\",
        \"is_enabled\": true,
        \"slack\": {
          \"url\": \"${SLACK_URL}\"
        }
      }
    }" > /dev/null 2>&1
  echo "  Webhook URL updated"
else
  DEST_RESPONSE=$(os_curl -X POST 'http://localhost:9200/_plugins/_notifications/configs' \
    -d "{
      \"config_id\": \"stoa-slack\",
      \"config\": {
        \"name\": \"STOA Slack Alerts\",
        \"description\": \"OpenSearch alerting → Slack #stoa-alerts\",
        \"config_type\": \"slack\",
        \"is_enabled\": true,
        \"slack\": {
          \"url\": \"${SLACK_URL}\"
        }
      }
    }")
  DEST_ID=$(echo "$DEST_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('config_id',''))" 2>/dev/null || true)

  if [ -z "$DEST_ID" ]; then
    echo "  ERROR: could not create Slack notification channel"
    echo "  Response: $DEST_RESPONSE"
    exit 1
  fi
fi
echo "  Channel ID: $DEST_ID"

# 2. Create monitors from monitors.json
echo ""
echo "[2/$TOTAL] Creating alerting monitors..."
MONITORS=$(cat "$SCRIPT_DIR/monitors.json")
COUNT=$(echo "$MONITORS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
echo "  Found $COUNT monitor definitions"

CREATED=0
SKIPPED=0
for i in $(seq 0 $((COUNT - 1))); do
  MONITOR_NAME=$(echo "$MONITORS" | python3 -c "import sys,json; print(json.load(sys.stdin)[$i]['name'])")

  # Check if monitor already exists
  SEARCH_RESP=$(os_curl -X POST 'http://localhost:9200/_plugins/_alerting/monitors/_search' \
    -d "{\"query\":{\"term\":{\"monitor.name.keyword\":\"$MONITOR_NAME\"}}}" 2>/dev/null || true)
  EXISTING_COUNT=$(echo "$SEARCH_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('hits',{}).get('total',{}).get('value',0))" 2>/dev/null || echo "0")

  if [ "$EXISTING_COUNT" -gt 0 ]; then
    echo "  [$((i+1))/$COUNT] $MONITOR_NAME — already exists, skipping"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  # Replace destination ID placeholder and create
  MONITOR_JSON=$(echo "$MONITORS" | python3 -c "
import sys, json
monitors = json.load(sys.stdin)
m = monitors[$i]
# Replace destination_id in all triggers/actions
for trigger in m.get('triggers', []):
    for action in trigger.get('actions', []):
        action['destination_id'] = '$DEST_ID'
json.dump(m, sys.stdout)
")

  RESP=$(os_curl -X POST 'http://localhost:9200/_plugins/_alerting/monitors' -d "$MONITOR_JSON")
  MON_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('_id','FAILED'))" 2>/dev/null || echo "FAILED")

  if [ "$MON_ID" = "FAILED" ]; then
    echo "  [$((i+1))/$COUNT] $MONITOR_NAME — FAILED"
    echo "    $RESP"
  else
    echo "  [$((i+1))/$COUNT] $MONITOR_NAME — created ($MON_ID)"
    CREATED=$((CREATED + 1))
  fi
done

# 3. Verify
echo ""
echo "[3/$TOTAL] Verifying monitors..."
VERIFY=$(os_curl -X POST 'http://localhost:9200/_plugins/_alerting/monitors/_search' \
  -d '{"query":{"match_all":{}},"size":20}')
TOTAL_MONITORS=$(echo "$VERIFY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('hits',{}).get('total',{}).get('value',0))" 2>/dev/null || echo "?")
echo "  Total monitors on cluster: $TOTAL_MONITORS"

# 4. Summary
echo ""
echo "[4/$TOTAL] Summary"
echo "  Destination: $DEST_ID (Slack)"
echo "  Created: $CREATED | Skipped: $SKIPPED"
echo ""
echo "=== Alerting bootstrap complete ==="
echo ""
echo "Monitors deployed:"
echo "  1. Gateway 5xx Error Spike    — every 5m, threshold >10"
echo "  2. Auth Failure Burst          — every 5m, threshold >20"
echo "  3. Slow Gateway Requests       — every 5m, threshold >10 (>2s)"
echo "  4. MCP Tool Errors             — every 5m, threshold >5"
echo "  5. Log Pipeline Dead           — every 15m, 0 docs = alert"
echo "  6. Arena Score Drop            — every 60m, score <80"
echo ""
echo "Manage in OSD: https://opensearch.gostoa.dev/_plugins/_alerting"
