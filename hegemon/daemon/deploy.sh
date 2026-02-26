#!/usr/bin/env bash
# Deploy HEGEMON daemon binary to a control plane VPS.
#
# Usage:
#   ./deploy.sh <host> [config_path]
#
# Prerequisites:
#   - Go 1.22+ installed locally
#   - SSH key access to target host
#   - config.yaml prepared (from config.example.yaml)
set -euo pipefail

HOST="${1:?Usage: deploy.sh <host> [config_path]}"
CONFIG="${2:-config.yaml}"
USER="${HEGEMON_USER:-hegemon}"
DEPLOY_DIR="/home/${USER}/hegemon"

echo "=== Building hegemon binary (linux/amd64) ==="
cd "$(dirname "$0")"
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -ldflags="-s -w" -o hegemon ./cmd/hegemon/
ls -lh hegemon
echo ""

echo "=== Deploying to ${USER}@${HOST} ==="
ssh "${USER}@${HOST}" "mkdir -p ${DEPLOY_DIR}"
scp hegemon "${USER}@${HOST}:${DEPLOY_DIR}/hegemon"
scp "${CONFIG}" "${USER}@${HOST}:${DEPLOY_DIR}/config.yaml"
echo ""

echo "=== Installing systemd service ==="
ssh "${USER}@${HOST}" "sudo tee /etc/systemd/system/hegemon.service > /dev/null" <<'SERVICE'
[Unit]
Description=HEGEMON AI Factory Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hegemon
Group=hegemon
WorkingDirectory=/home/hegemon/hegemon
ExecStart=/home/hegemon/hegemon/hegemon --config /home/hegemon/hegemon/config.yaml
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=hegemon

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/hegemon/hegemon

# Graceful shutdown
TimeoutStopSec=30
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
SERVICE

ssh "${USER}@${HOST}" "sudo systemctl daemon-reload && sudo systemctl enable hegemon"
echo ""

echo "=== Starting daemon ==="
ssh "${USER}@${HOST}" "sudo systemctl restart hegemon && sleep 2 && sudo systemctl status hegemon --no-pager"
echo ""

echo "=== Deployed successfully ==="
echo "Logs: ssh ${USER}@${HOST} 'journalctl -u hegemon -f'"
echo "Stop: ssh ${USER}@${HOST} 'sudo systemctl stop hegemon'"

# Cleanup local binary
rm -f hegemon
