#!/usr/bin/env bash
# Deploy node_exporter on all STOA VPS and set up cron push to Pushgateway
#
# Installs node_exporter as a systemd service on each VPS, plus a cron job
# that pushes metrics to pushgateway.gostoa.dev every 60 seconds.
#
# Prerequisites:
#   - SSH key: ~/.ssh/id_ed25519_stoa
#   - Pushgateway ingress deployed: https://pushgateway.gostoa.dev
#   - Pushgateway auth in Infisical: /pushgateway/PUSHGATEWAY_AUTH
#
# Usage: ./deploy/vps/monitoring/deploy-node-exporter.sh [--dry-run] [--only IP]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY=~/.ssh/id_ed25519_stoa
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -i $SSH_KEY"

NODE_EXPORTER_VERSION="1.8.2"
PUSHGATEWAY_URL="https://pushgateway.gostoa.dev"
PUSHGATEWAY_AUTH="arena:arena-push-2026"
PUSH_INTERVAL=60  # seconds

DRY_RUN=false
ONLY_IP=""

# --- VPS Inventory ---
# Format: "IP|SSH_USER|LABEL"
VPS_LIST=(
  # Contabo HEGEMON workers
  "194.163.161.85|root|contabo-runner-github"
  "213.199.45.108|root|contabo-infisical"
  "144.91.73.37|hegemon|contabo-hegemon-w1"
  "164.68.121.123|hegemon|contabo-hegemon-w2"
  "167.86.115.51|hegemon|contabo-hegemon-w3"
  "207.180.255.223|hegemon|contabo-hegemon-w4"
  "207.180.246.92|hegemon|contabo-hegemon-w5"
  # OVH Gateway VPS
  "51.83.45.13|debian|ovh-stoa-gateway"
  "51.195.43.130|stoa|ovh-kong"
  "135.125.204.169|stoa|ovh-agentgateway"
  "54.36.209.237|debian|ovh-gravitee"
  "94.23.107.106|debian|ovh-bench"
  # OVH Tooling VPS
  "51.254.139.205|debian|ovh-n8n-tooling"
  "51.255.193.129|debian|ovh-vault"
)

# --- Parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --only) ONLY_IP="$2"; shift 2 ;;
    *) echo "Usage: $0 [--dry-run] [--only IP]"; exit 1 ;;
  esac
done

# --- Colors ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[-]${NC} $*"; }

# --- Remote install script (runs on each VPS) ---
generate_remote_script() {
  local label="$1"
  cat <<'REMOTE_EOF'
#!/usr/bin/env bash
set -euo pipefail

NODE_EXPORTER_VERSION="__VERSION__"
PUSHGATEWAY_URL="__PUSHGATEWAY_URL__"
PUSHGATEWAY_AUTH="__PUSHGATEWAY_AUTH__"
PUSH_INTERVAL="__PUSH_INTERVAL__"
INSTANCE_LABEL="__LABEL__"

echo "[1/5] Installing node_exporter ${NODE_EXPORTER_VERSION}..."
if command -v node_exporter &>/dev/null; then
  CURRENT=$(node_exporter --version 2>&1 | head -1 | grep -oP 'version \K[0-9.]+' || echo "unknown")
  echo "  node_exporter already installed (${CURRENT})"
  if [[ "$CURRENT" == "$NODE_EXPORTER_VERSION" ]]; then
    echo "  Already at target version, skipping download"
    SKIP_DOWNLOAD=true
  else
    SKIP_DOWNLOAD=false
  fi
else
  SKIP_DOWNLOAD=false
fi

if [[ "${SKIP_DOWNLOAD:-false}" != "true" ]]; then
  ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
  TARBALL="node_exporter-${NODE_EXPORTER_VERSION}.linux-${ARCH}.tar.gz"
  cd /tmp
  curl -sLO "https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/${TARBALL}"
  tar xzf "${TARBALL}"
  cp "node_exporter-${NODE_EXPORTER_VERSION}.linux-${ARCH}/node_exporter" /usr/local/bin/
  rm -rf "node_exporter-${NODE_EXPORTER_VERSION}.linux-${ARCH}" "${TARBALL}"
  chmod +x /usr/local/bin/node_exporter
fi

echo "[2/5] Creating systemd service..."
cat > /etc/systemd/system/node_exporter.service <<EOF
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/node_exporter \\
  --web.listen-address=127.0.0.1:9100 \\
  --collector.systemd \\
  --collector.processes \\
  --no-collector.arp \\
  --no-collector.infiniband \\
  --no-collector.ipvs \\
  --no-collector.nfs \\
  --no-collector.nfsd \\
  --no-collector.zfs
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now node_exporter
echo "  node_exporter listening on 127.0.0.1:9100"

echo "[3/5] Installing push script..."
mkdir -p /opt/monitoring
cat > /opt/monitoring/push-metrics.sh <<'PUSH_EOF'
#!/usr/bin/env bash
# Push node_exporter metrics to Pushgateway
set -euo pipefail

PUSHGATEWAY_URL="__PUSHGATEWAY_URL__"
PUSHGATEWAY_AUTH="__PUSHGATEWAY_AUTH__"
INSTANCE_LABEL="__LABEL__"
HOSTNAME_LABEL=$(hostname -s)

# Scrape local node_exporter and push to Pushgateway
# job=node_exporter, instance=<label>
METRICS=$(curl -sf http://127.0.0.1:9100/metrics 2>/dev/null) || {
  echo "$(date -Iseconds) ERROR: node_exporter unreachable" >> /var/log/push-metrics.log
  exit 1
}

# Push to Pushgateway with grouping keys
echo "$METRICS" | curl -sf \
  -u "$PUSHGATEWAY_AUTH" \
  --data-binary @- \
  "${PUSHGATEWAY_URL}/metrics/job/node_exporter/instance/${INSTANCE_LABEL}/hostname/${HOSTNAME_LABEL}" \
  2>/dev/null || {
  echo "$(date -Iseconds) ERROR: push failed" >> /var/log/push-metrics.log
  exit 1
}
PUSH_EOF
chmod +x /opt/monitoring/push-metrics.sh

# Replace placeholders in push script
sed -i "s|__PUSHGATEWAY_URL__|${PUSHGATEWAY_URL}|g" /opt/monitoring/push-metrics.sh
sed -i "s|__PUSHGATEWAY_AUTH__|${PUSHGATEWAY_AUTH}|g" /opt/monitoring/push-metrics.sh
sed -i "s|__LABEL__|${INSTANCE_LABEL}|g" /opt/monitoring/push-metrics.sh

echo "[4/5] Setting up systemd timer (every ${PUSH_INTERVAL}s)..."
cat > /etc/systemd/system/push-metrics.service <<EOF
[Unit]
Description=Push node_exporter metrics to Pushgateway
After=node_exporter.service

[Service]
Type=oneshot
ExecStart=/opt/monitoring/push-metrics.sh
EOF

cat > /etc/systemd/system/push-metrics.timer <<EOF
[Unit]
Description=Push metrics every ${PUSH_INTERVAL} seconds

[Timer]
OnBootSec=30
OnUnitActiveSec=${PUSH_INTERVAL}s
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now push-metrics.timer

echo "[5/5] Verifying..."
sleep 3
if curl -sf -o /dev/null http://127.0.0.1:9100/metrics; then
  echo "  node_exporter: OK"
else
  echo "  node_exporter: FAILED (may need a few more seconds to start)"
fi

# Test push
/opt/monitoring/push-metrics.sh && echo "  push to Pushgateway: OK" || echo "  push to Pushgateway: FAILED (non-blocking)"

echo ""
echo "Done! Metrics will be pushed every ${PUSH_INTERVAL}s to ${PUSHGATEWAY_URL}"
echo "  job=node_exporter instance=${INSTANCE_LABEL}"
REMOTE_EOF
}

# --- Main ---
log "Deploying node_exporter to ${#VPS_LIST[@]} VPS servers"
log "Pushgateway: ${PUSHGATEWAY_URL}"
log "Push interval: ${PUSH_INTERVAL}s"
echo ""

SUCCESS=0
FAILED=0

for entry in "${VPS_LIST[@]}"; do
  IFS='|' read -r ip user label <<< "$entry"

  # Filter if --only specified
  if [[ -n "$ONLY_IP" && "$ip" != "$ONLY_IP" ]]; then
    continue
  fi

  log "--- ${label} (${ip}) ---"

  if $DRY_RUN; then
    warn "DRY RUN: would deploy node_exporter to ${user}@${ip}"
    continue
  fi

  # Test SSH connectivity
  if ! ssh $SSH_OPTS "${user}@${ip}" "echo ok" &>/dev/null; then
    err "Cannot SSH to ${user}@${ip} — skipping"
    ((FAILED++))
    continue
  fi

  # Generate and upload script
  REMOTE_SCRIPT=$(generate_remote_script "$label")
  REMOTE_SCRIPT="${REMOTE_SCRIPT//__VERSION__/$NODE_EXPORTER_VERSION}"
  REMOTE_SCRIPT="${REMOTE_SCRIPT//__PUSHGATEWAY_URL__/$PUSHGATEWAY_URL}"
  REMOTE_SCRIPT="${REMOTE_SCRIPT//__PUSHGATEWAY_AUTH__/$PUSHGATEWAY_AUTH}"
  REMOTE_SCRIPT="${REMOTE_SCRIPT//__PUSH_INTERVAL__/$PUSH_INTERVAL}"
  REMOTE_SCRIPT="${REMOTE_SCRIPT//__LABEL__/$label}"

  echo "$REMOTE_SCRIPT" | ssh $SSH_OPTS "${user}@${ip}" "cat > /tmp/install-node-exporter.sh && chmod +x /tmp/install-node-exporter.sh"

  # Execute (with sudo if not root)
  if [[ "$user" == "root" ]]; then
    ssh $SSH_OPTS "${user}@${ip}" "bash /tmp/install-node-exporter.sh" && ((SUCCESS++)) || ((FAILED++))
  else
    ssh $SSH_OPTS "${user}@${ip}" "sudo bash /tmp/install-node-exporter.sh" && ((SUCCESS++)) || ((FAILED++))
  fi

  echo ""
done

echo ""
log "========================================="
log "Deployment complete: ${SUCCESS} OK, ${FAILED} failed"
log "========================================="
log ""
log "Next steps:"
log "  1. Verify metrics in Pushgateway: curl -su '${PUSHGATEWAY_AUTH}' ${PUSHGATEWAY_URL}/metrics | grep node_cpu"
log "  2. Import Grafana dashboard: deploy/vps/monitoring/vps-fleet-dashboard.json"
log "  3. Check timer status: ssh <vps> systemctl status push-metrics.timer"
