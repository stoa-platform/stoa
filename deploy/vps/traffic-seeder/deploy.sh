#!/usr/bin/env bash
# Deploy realistic traffic seeder to VPS (worker-3: 164.68.121.123)
#
# Runs as cron job on VPS, generating sidecar + connect traffic.
# Prerequisites:
#   - stoa-gateway running on VPS with STOA_MODE=sidecar
#   - stoa-connect running on VPS (systemd)
#   - Vault Agent rendering /opt/secrets/traffic-seeder.env
#   - Python 3.11+ with pip
#
# Usage: ./deploy.sh [VPS_HOST] [SSH_KEY]
#   VPS_HOST: target VPS IP (default: 164.68.121.123 = worker-3)
#   SSH_KEY:  SSH private key path (default: ~/.ssh/id_ed25519_stoa)

set -euo pipefail

VPS_HOST="${1:-164.68.121.123}"
SSH_KEY="${2:-$HOME/.ssh/id_ed25519_stoa}"
VPS_USER="hegemon"
REMOTE_DIR="/opt/stoa/traffic-seeder"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "=== Deploying traffic seeder to $VPS_HOST ==="

# 1. Create remote directory
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "sudo mkdir -p $REMOTE_DIR && sudo chown $VPS_USER:$VPS_USER $REMOTE_DIR"

# 2. Copy seeder scripts
scp -i "$SSH_KEY" \
    "$REPO_ROOT/scripts/traffic/realistic-seeder.py" \
    "$REPO_ROOT/scripts/traffic/scenarios.py" \
    "$REPO_ROOT/scripts/traffic/auth_helpers.py" \
    "$VPS_USER@$VPS_HOST:$REMOTE_DIR/"

# 3. Create package init files for imports
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "
    mkdir -p $REMOTE_DIR/scripts/traffic
    cp $REMOTE_DIR/realistic-seeder.py $REMOTE_DIR/scripts/traffic/
    cp $REMOTE_DIR/scenarios.py $REMOTE_DIR/scripts/traffic/
    cp $REMOTE_DIR/auth_helpers.py $REMOTE_DIR/scripts/traffic/
    touch $REMOTE_DIR/scripts/__init__.py $REMOTE_DIR/scripts/traffic/__init__.py
"

# 4. Install Python dependencies
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "
    pip3 install --user requests==2.31.0 PyJWT==2.9.0 cryptography==43.0.0 2>/dev/null || \
    pip install --user requests==2.31.0 PyJWT==2.9.0 cryptography==43.0.0
"

# 5. Create cron wrapper that sources Vault secrets
cat <<'CRON_SCRIPT' | ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cat > $REMOTE_DIR/run-seeder.sh && chmod +x $REMOTE_DIR/run-seeder.sh"
#!/usr/bin/env bash
# Cron wrapper — sources Vault Agent secrets, then runs seeder in VPS mode.
set -euo pipefail

# Source secrets from Vault Agent (if available)
if [ -f /opt/secrets/traffic-seeder.env ]; then
    set -a
    source /opt/secrets/traffic-seeder.env
    set +a
fi

cd /opt/stoa/traffic-seeder
exec python3 realistic-seeder.py --mode vps "$@" >> /var/log/stoa/traffic-seeder.log 2>&1
CRON_SCRIPT

# 6. Create log directory
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "sudo mkdir -p /var/log/stoa && sudo chown $VPS_USER:$VPS_USER /var/log/stoa"

# 7. Install cron job (every 10 minutes)
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "
    (crontab -l 2>/dev/null | grep -v 'traffic-seeder'; echo '*/10 * * * * $REMOTE_DIR/run-seeder.sh') | crontab -
"

echo "=== Traffic seeder deployed ==="
echo "Cron: */10 * * * * (VPS mode: sidecar + connect)"
echo "Logs: /var/log/stoa/traffic-seeder.log"
echo ""
echo "Manual test:"
echo "  ssh -i $SSH_KEY $VPS_USER@$VPS_HOST '$REMOTE_DIR/run-seeder.sh --dry-run'"
echo ""
echo "To include webMethods:"
echo "  ssh -i $SSH_KEY $VPS_USER@$VPS_HOST '$REMOTE_DIR/run-seeder.sh --include-webmethods'"
