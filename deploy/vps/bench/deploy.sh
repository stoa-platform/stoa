#!/usr/bin/env bash
# Deploy Arena bench sidecar to VPS (co-located benchmarks)
# Each VPS benchmarks only its local gateway(s) and pushes to pushgateway.gostoa.dev
#
# Prerequisites:
#   - SSH key: ~/.ssh/id_ed25519_stoa
#   - Pushgateway ingress deployed: https://pushgateway.gostoa.dev
#   - Docker installed on VPS with ghcr.io login
#   - Echo server deployed: ./deploy/vps/echo/deploy-all.sh
#
# Usage: ./deploy/vps/bench/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SSH_KEY=~/.ssh/id_ed25519_stoa

# VPS configs: name, IP, GATEWAYS JSON
# stoa-vps and kong-vps share the same VPS (51.83.45.13)
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

# Pre-check: verify pushgateway is reachable
echo "Pre-check: Pushgateway health..."
if curl -sf "${PUSHGATEWAY_URL}/-/healthy" > /dev/null 2>&1; then
  echo "  Pushgateway OK"
else
  echo "  WARNING: Pushgateway unreachable at ${PUSHGATEWAY_URL}"
  echo "  VPS benches will run but can't push metrics. Fix ingress/TLS first."
fi

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

  echo "  [1/5] Creating remote directory..."
  ssh -i "$SSH_KEY" "debian@${VPS_IP}" "mkdir -p ${REMOTE_DIR}/scripts"

  echo "  [2/5] Copying scripts + docker-compose..."
  scp -i "$SSH_KEY" -q \
    "$REPO_ROOT/scripts/traffic/arena/benchmark.js" \
    "$REPO_ROOT/scripts/traffic/arena/run-arena.sh" \
    "$REPO_ROOT/scripts/traffic/arena/run-arena.py" \
    "debian@${VPS_IP}:${REMOTE_DIR}/scripts/"
  scp -i "$SSH_KEY" -q "$SCRIPT_DIR/docker-compose.yml" "debian@${VPS_IP}:${REMOTE_DIR}/"

  echo "  [3/5] Creating .env file..."
  ssh -i "$SSH_KEY" "debian@${VPS_IP}" "cat > ${REMOTE_DIR}/.env <<ENVEOF
PUSHGATEWAY_URL=${PUSHGATEWAY_URL}
PUSHGATEWAY_AUTH=arena:arena-push-2026
RUNS=5
DISCARD_FIRST=1
TIMEOUT=5
GATEWAYS=${COMBINED_GATEWAYS}
ENVEOF"

  echo "  [4/5] Pulling arena-bench image..."
  ssh -i "$SSH_KEY" "debian@${VPS_IP}" "docker pull ghcr.io/stoa-platform/arena-bench:0.1.0 2>/dev/null || echo 'Pull failed — ensure docker login ghcr.io'"

  echo "  [5/5] Installing systemd timer (every 30 min)..."
  ssh -i "$SSH_KEY" "debian@${VPS_IP}" "sudo tee /etc/systemd/system/arena-bench.service > /dev/null <<'SVCEOF'
[Unit]
Description=Gateway Arena Benchmark
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=${REMOTE_DIR}
ExecStart=/usr/bin/docker compose run --rm arena
User=debian
StandardOutput=append:/var/log/arena-bench.log
StandardError=append:/var/log/arena-bench.log
SVCEOF

sudo tee /etc/systemd/system/arena-bench.timer > /dev/null <<'TMREOF'
[Unit]
Description=Run Arena Benchmark every 30 minutes

[Timer]
OnCalendar=*:00,30
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
TMREOF

sudo systemctl daemon-reload
sudo systemctl enable --now arena-bench.timer"

  echo "  Done: $VPS_IP"
done

echo ""
echo "=== VPS Deploy Complete ==="
echo "Timer: every 30 min (systemd) on each VPS"
echo "Pushgateway: ${PUSHGATEWAY_URL}"
echo ""
echo "Verify (manual run):"
echo "  ssh -i $SSH_KEY debian@51.83.45.13 'cd /opt/arena && docker compose run --rm arena'"
echo "  ssh -i $SSH_KEY debian@54.36.209.237 'cd /opt/arena && docker compose run --rm arena'"
echo "  curl -sf -u arena:arena-push-2026 https://pushgateway.gostoa.dev/metrics | grep gateway_arena_score"
