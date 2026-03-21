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
# Each gateway is isolated on its own VPS for reliable benchmarking (no noisy neighbor)
# Gravitee removed: scores near-zero on AI dimensions, 50% availability issues
declare -A VPS_IPS=(
  ["stoa-vps"]="51.83.45.13"
  ["kong-vps"]="51.195.43.130"
  ["agentgateway-vps"]="135.125.204.169"
  ["bench-vps"]="94.23.107.106"
)

declare -A VPS_GATEWAYS=(
  ["stoa-vps"]='[{"name":"stoa-vps","health":"http://localhost:8080/health","proxy":"http://localhost:8080/echo/get"}]'
  ["kong-vps"]='[{"name":"kong-vps","health":"http://localhost:8001/status","proxy":"http://localhost:8000/echo/get"}]'
  ["agentgateway-vps"]='[{"name":"agentgateway-vps","health":"http://localhost:3000/health","proxy":"http://localhost:3000/echo/get"}]'
  ["bench-vps"]='[{"name":"stoa-vps","health":"http://51.83.45.13:8080/health","proxy":"http://51.83.45.13:8080/echo/get"},{"name":"kong-vps","health":"http://51.195.43.130:8001/status","proxy":"http://51.195.43.130:8000/echo/get"},{"name":"agentgateway-vps","health":"http://135.125.204.169:3000/health","proxy":"http://135.125.204.169:3000/echo/get"}]'
)

# Enterprise GATEWAYS JSON (L1 — with mcp_base, admin_base, features)
# Feature declarations match K8s cronjob-enterprise.yaml
declare -A VPS_GATEWAYS_ENTERPRISE=(
  ["stoa-vps"]='[{"name":"stoa-vps","target":"http://localhost:8080","mcp_base":"http://localhost:8080/mcp","mcp_protocol":"stoa","admin_base":"http://localhost:8080","health":"http://localhost:8080/health","features":["llm_routing","llm_cost","llm_circuit_breaker","native_tools_crud","api_bridge","uac_binding","pii_detection","distributed_tracing","prompt_cache","skills_lifecycle","federation","diagnostic"]}]'
  ["kong-vps"]='[{"name":"kong-vps","target":"http://localhost:8000","mcp_base":null,"mcp_protocol":null,"admin_base":null,"health":"http://localhost:8001/status","features":[]}]'
  ["agentgateway-vps"]='[{"name":"agentgateway-vps","target":"http://localhost:3000","mcp_base":"http://localhost:3000/mcp","mcp_protocol":"streamable-http","admin_base":"http://localhost:15000","health":"http://localhost:3000/health","features":["llm_routing","llm_cost","llm_circuit_breaker","native_tools_crud","api_bridge","pii_detection","distributed_tracing","federation"]}]'
  ["bench-vps"]='[{"name":"stoa-vps","target":"http://51.83.45.13:8080","mcp_base":"http://51.83.45.13:8080/mcp","mcp_protocol":"stoa","admin_base":"http://51.83.45.13:8080","health":"http://51.83.45.13:8080/health","features":["llm_routing","llm_cost","llm_circuit_breaker","native_tools_crud","api_bridge","uac_binding","pii_detection","distributed_tracing","prompt_cache","skills_lifecycle","federation","diagnostic"]},{"name":"kong-vps","target":"http://51.195.43.130:8000","mcp_base":null,"mcp_protocol":null,"admin_base":null,"health":"http://51.195.43.130:8001/status","features":[]},{"name":"agentgateway-vps","target":"http://135.125.204.169:3000","mcp_base":"http://135.125.204.169:3000/mcp","mcp_protocol":"streamable-http","admin_base":"http://135.125.204.169:15000","health":"http://135.125.204.169:3000/health","features":["llm_routing","llm_cost","llm_circuit_breaker","native_tools_crud","api_bridge","pii_detection","distributed_tracing","federation"]}]'
)

# Unique VPS IPs (each gateway isolated on its own VPS)
declare -A UNIQUE_VPS=(
  ["51.83.45.13"]="stoa-vps"
  ["51.195.43.130"]="kong-vps"
  ["135.125.204.169"]="agentgateway-vps"
  ["94.23.107.106"]="bench-vps"
)

# SSH users per VPS IP (OVH gateway VPS = debian, OVH dev VPS = stoa)
declare -A VPS_SSH_USER=(
  ["51.83.45.13"]="debian"
  ["51.195.43.130"]="stoa"
  ["135.125.204.169"]="stoa"
  ["94.23.107.106"]="debian"
)

# Instance labels per VPS IP (prevent Pushgateway push overwrites between clusters)
declare -A VPS_INSTANCE=(
  ["51.83.45.13"]="vps-stoa"
  ["51.195.43.130"]="vps-kong"
  ["135.125.204.169"]="vps-agentgateway"
  ["94.23.107.106"]="vps-bench"
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

  # Build combined GATEWAYS JSON for this VPS (L0)
  COMBINED_GATEWAYS="["
  first=true
  for gw_name in $GATEWAY_NAMES; do
    if [ "$first" = true ]; then
      first=false
    else
      COMBINED_GATEWAYS="${COMBINED_GATEWAYS},"
    fi
    gw_json=$(echo "${VPS_GATEWAYS[$gw_name]}" | jq -c '.[0]')
    COMBINED_GATEWAYS="${COMBINED_GATEWAYS}${gw_json}"
  done
  COMBINED_GATEWAYS="${COMBINED_GATEWAYS}]"

  # Build combined enterprise GATEWAYS JSON for this VPS (L1)
  COMBINED_GATEWAYS_ENT="["
  first=true
  for gw_name in $GATEWAY_NAMES; do
    if [ "$first" = true ]; then
      first=false
    else
      COMBINED_GATEWAYS_ENT="${COMBINED_GATEWAYS_ENT},"
    fi
    gw_json=$(echo "${VPS_GATEWAYS_ENTERPRISE[$gw_name]}" | jq -c '.[0]')
    COMBINED_GATEWAYS_ENT="${COMBINED_GATEWAYS_ENT}${gw_json}"
  done
  COMBINED_GATEWAYS_ENT="${COMBINED_GATEWAYS_ENT}]"

  echo "  [1/7] Creating remote directory..."
  ssh -i "$SSH_KEY" "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}" "mkdir -p ${REMOTE_DIR}/scripts"

  echo "  [2/7] Copying scripts + docker-compose..."
  scp -i "$SSH_KEY" -q \
    "$REPO_ROOT/scripts/traffic/arena/benchmark.js" \
    "$REPO_ROOT/scripts/traffic/arena/run-arena.sh" \
    "$REPO_ROOT/scripts/traffic/arena/run-arena.py" \
    "$REPO_ROOT/scripts/traffic/arena/benchmark-enterprise.js" \
    "$REPO_ROOT/scripts/traffic/arena/run-arena-enterprise.sh" \
    "$REPO_ROOT/scripts/traffic/arena/run-arena-enterprise.py" \
    "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}:${REMOTE_DIR}/scripts/"
  scp -i "$SSH_KEY" -q \
    "$SCRIPT_DIR/docker-compose.yml" \
    "$SCRIPT_DIR/docker-compose.enterprise.yml" \
    "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}:${REMOTE_DIR}/"

  INSTANCE_LABEL="${VPS_INSTANCE[$VPS_IP]}"
  echo "  [3/7] Creating .env file (L0, instance=$INSTANCE_LABEL)..."
  ssh -i "$SSH_KEY" "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}" "cat > ${REMOTE_DIR}/.env <<ENVEOF
PUSHGATEWAY_URL=${PUSHGATEWAY_URL}
PUSHGATEWAY_AUTH=arena:arena-push-2026
RUNS=5
DISCARD_FIRST=1
TIMEOUT=5
ARENA_INSTANCE=${INSTANCE_LABEL}
GATEWAYS=${COMBINED_GATEWAYS}
OPENSEARCH_ENABLED=\${OPENSEARCH_ENABLED:-false}
OPENSEARCH_URL=\${OPENSEARCH_URL:-}
OPENSEARCH_USER=\${OPENSEARCH_USER:-}
OPENSEARCH_PASSWORD=\${OPENSEARCH_PASSWORD:-}
ENVEOF"

  # bench-vps uses centralized OpenSearch (OVH K8s prod)
  if [ "$VPS_IP" = "94.23.107.106" ]; then
    ssh -i "$SSH_KEY" "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}" "sed -i 's|OPENSEARCH_ENABLED=.*|OPENSEARCH_ENABLED=true|; s|OPENSEARCH_URL=.*|OPENSEARCH_URL=https://opensearch-api.gostoa.dev|' ${REMOTE_DIR}/.env"
    echo "    (OpenSearch credentials must be set manually from Infisical: prod/opensearch/ADMIN_PASSWORD)"
  fi

  echo "  [4/7] Creating .env.enterprise file (L1, instance=$INSTANCE_LABEL)..."
  ssh -i "$SSH_KEY" "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}" "cat > ${REMOTE_DIR}/.env.enterprise <<ENVEOF
PUSHGATEWAY_URL=${PUSHGATEWAY_URL}
PUSHGATEWAY_AUTH=arena:arena-push-2026
RUNS=5
DISCARD_FIRST=1
TIMEOUT=10
ARENA_INSTANCE=${INSTANCE_LABEL}
GATEWAYS=${COMBINED_GATEWAYS_ENT}
OPENSEARCH_ENABLED=\${OPENSEARCH_ENABLED:-false}
OPENSEARCH_URL=\${OPENSEARCH_URL:-}
OPENSEARCH_USER=\${OPENSEARCH_USER:-}
OPENSEARCH_PASSWORD=\${OPENSEARCH_PASSWORD:-}
ENVEOF"

  # bench-vps uses centralized OpenSearch (OVH K8s prod)
  if [ "$VPS_IP" = "94.23.107.106" ]; then
    ssh -i "$SSH_KEY" "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}" "sed -i 's|OPENSEARCH_ENABLED=.*|OPENSEARCH_ENABLED=true|; s|OPENSEARCH_URL=.*|OPENSEARCH_URL=https://opensearch-api.gostoa.dev|' ${REMOTE_DIR}/.env.enterprise"
  fi

  echo "  [5/7] Pulling arena-bench image..."
  ssh -i "$SSH_KEY" "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}" "docker pull ghcr.io/stoa-platform/arena-bench:0.2.0 2>/dev/null || echo 'Pull failed — ensure docker login ghcr.io'"

  echo "  [6/7] Installing L0 systemd timer (every 30 min)..."
  ssh -i "$SSH_KEY" "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}" "sudo tee /etc/systemd/system/arena-bench.service > /dev/null <<'SVCEOF'
[Unit]
Description=Gateway Arena Benchmark (L0)
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
Description=Run Arena Benchmark every 30 minutes (L0)

[Timer]
OnCalendar=*:00,30
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
TMREOF

sudo systemctl daemon-reload
sudo systemctl enable --now arena-bench.timer"

  echo "  [7/7] Installing L1 enterprise systemd timer (hourly)..."
  ssh -i "$SSH_KEY" "${VPS_SSH_USER[$VPS_IP]}@${VPS_IP}" "sudo tee /etc/systemd/system/arena-bench-enterprise.service > /dev/null <<'SVCEOF'
[Unit]
Description=Gateway Arena Enterprise Benchmark (L1)
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=${REMOTE_DIR}
ExecStart=/usr/bin/docker compose -f docker-compose.enterprise.yml run --rm arena-enterprise
User=debian
StandardOutput=append:/var/log/arena-bench-enterprise.log
StandardError=append:/var/log/arena-bench-enterprise.log
SVCEOF

sudo tee /etc/systemd/system/arena-bench-enterprise.timer > /dev/null <<'TMREOF'
[Unit]
Description=Run Arena Enterprise Benchmark hourly (L1)

[Timer]
OnCalendar=*:00
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
TMREOF

sudo systemctl daemon-reload
sudo systemctl enable --now arena-bench-enterprise.timer"

  echo "  Done: $VPS_IP"
done

echo ""
echo "=== VPS Deploy Complete ==="
echo "Timers: L0 every 30 min + L1 enterprise hourly on each VPS"
echo "Pushgateway: ${PUSHGATEWAY_URL}"
echo ""
echo "Verify (manual run):"
echo "  ssh -i $SSH_KEY debian@51.83.45.13 'cd /opt/arena && docker compose run --rm arena'        # STOA"
echo "  ssh -i $SSH_KEY stoa@51.195.43.130 'cd /opt/arena && docker compose run --rm arena'         # Kong"
echo "  ssh -i $SSH_KEY stoa@135.125.204.169 'cd /opt/arena && docker compose run --rm arena'       # agentgateway"
echo "  ssh -i $SSH_KEY debian@94.23.107.106 'cd /opt/arena && docker compose run --rm arena'       # bench (all 3 remote)"
echo "  curl -sf -u arena:arena-push-2026 https://pushgateway.gostoa.dev/metrics | grep enterprise_dimension"
