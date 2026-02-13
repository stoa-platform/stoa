#!/usr/bin/env bash
# Deploy Arena bench sidecar to 3 VPS (co-located benchmarks)
# Usage: ./deploy/vps/bench/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# VPS configs: name, IP, GATEWAYS JSON
declare -A VPS_IPS=(
  ["stoa-vps"]="51.83.45.13"
  ["kong-vps"]="51.83.45.13"
  ["gravitee-vps"]="54.36.209.237"
)

declare -A VPS_GATEWAYS=(
  ["stoa-vps"]='[{"name":"stoa-vps","health":"http://localhost:8080/health","proxy":"http://localhost:8080/echo/get"}]'
  ["kong-vps"]='[{"name":"kong-vps","health":"http://localhost:8001/status","proxy":"http://localhost:8000/echo/get"}]'
  ["gravitee-vps"]='[{"name":"gravitee-vps","health":"http://localhost:8083/management/organizations/DEFAULT/environments/DEFAULT","proxy":"http://localhost:8082/echo/get"}]'
)

# Unique VPS IPs (stoa and kong share the same VPS)
declare -A UNIQUE_VPS=(
  ["51.83.45.13"]="stoa-vps kong-vps"
  ["54.36.209.237"]="gravitee-vps"
)

REMOTE_DIR="/opt/arena"
PUSHGATEWAY_URL="https://pushgateway.gostoa.dev"

echo "=== Arena VPS Bench Deploy ==="

for VPS_IP in "${!UNIQUE_VPS[@]}"; do
  GATEWAY_NAMES="${UNIQUE_VPS[$VPS_IP]}"
  echo ""
  echo "--- Deploying to $VPS_IP (gateways: $GATEWAY_NAMES) ---"

  # Build combined GATEWAYS JSON for this VPS
  COMBINED_GATEWAYS="["
  first=true
  for gw_name in $GATEWAY_NAMES; do
    if [ "$first" = true ]; then
      first=false
    else
      COMBINED_GATEWAYS="${COMBINED_GATEWAYS},"
    fi
    # Strip outer brackets and add
    gw_json=$(echo "${VPS_GATEWAYS[$gw_name]}" | jq -c '.[0]')
    COMBINED_GATEWAYS="${COMBINED_GATEWAYS}${gw_json}"
  done
  COMBINED_GATEWAYS="${COMBINED_GATEWAYS}]"

  echo "  [1/4] Creating remote directory..."
  ssh "root@${VPS_IP}" "mkdir -p ${REMOTE_DIR}/scripts"

  echo "  [2/4] Copying scripts + docker-compose..."
  scp -q "$REPO_ROOT/scripts/traffic/arena/benchmark.js" "root@${VPS_IP}:${REMOTE_DIR}/scripts/"
  scp -q "$REPO_ROOT/scripts/traffic/arena/run-arena.sh" "root@${VPS_IP}:${REMOTE_DIR}/scripts/"
  scp -q "$SCRIPT_DIR/docker-compose.yml" "root@${VPS_IP}:${REMOTE_DIR}/"

  echo "  [3/4] Creating .env file..."
  ssh "root@${VPS_IP}" "cat > ${REMOTE_DIR}/.env <<ENVEOF
PUSHGATEWAY_URL=${PUSHGATEWAY_URL}
RUNS=5
DISCARD_FIRST=1
TIMEOUT=5
GATEWAYS=${COMBINED_GATEWAYS}
ENVEOF"

  echo "  [4/4] Installing crontab..."
  CRON_LINE="*/30 * * * * cd ${REMOTE_DIR} && docker compose run --rm arena >> /var/log/arena-bench.log 2>&1"
  ssh "root@${VPS_IP}" "(crontab -l 2>/dev/null | grep -v arena || true; echo '${CRON_LINE}') | crontab -"

  echo "  Done: $VPS_IP"
done

echo ""
echo "=== VPS Deploy Complete ==="
echo "Cron schedule: */30 * * * * on each VPS"
echo "Pushgateway: ${PUSHGATEWAY_URL}"
echo ""
echo "Verify:"
echo "  ssh root@51.83.45.13 'cd /opt/arena && docker compose run --rm arena'"
echo "  ssh root@54.36.209.237 'cd /opt/arena && docker compose run --rm arena'"
echo "  curl -sf https://pushgateway.gostoa.dev/metrics | grep gateway_arena_score"
