#!/bin/bash
# =============================================================================
# Deploy Portainer CE — VPS Fleet Observability (CAB-1874)
# =============================================================================
# Phase 1: Portainer server on spare-gra-vps (Traefik TLS)
# Phase 2: Agents on all VPS (Docker socket + UFW firewall)
# Prerequisites: DNS portainer.gostoa.dev → 51.255.193.129
# =============================================================================
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_stoa}"
PORTAINER_HOST="debian@51.255.193.129"
PORTAINER_SERVER_IP="51.255.193.129"
REMOTE_DIR="/opt/portainer"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

log() { echo "[PORTAINER] $1"; }

# --- Phase 1: Deploy Portainer server ---
log "Phase 1: Deploying Portainer CE on spare-gra-vps..."

ssh -i "$SSH_KEY" "$PORTAINER_HOST" "sudo mkdir -p $REMOTE_DIR"
scp -i "$SSH_KEY" "$SCRIPT_DIR/docker-compose.yml" "$PORTAINER_HOST:/tmp/portainer-compose.yml"
ssh -i "$SSH_KEY" "$PORTAINER_HOST" "sudo mv /tmp/portainer-compose.yml $REMOTE_DIR/docker-compose.yml"

ssh -i "$SSH_KEY" "$PORTAINER_HOST" bash <<'REMOTE'
set -euo pipefail
cd /opt/portainer

if ! docker network inspect n8n_default >/dev/null 2>&1; then
  echo "[ERROR] Traefik network 'n8n_default' not found. Is n8n stack running?"
  exit 1
fi

docker compose pull
docker compose up -d
echo "[PORTAINER] Waiting for startup..."
sleep 5

if docker ps --filter name=portainer --format '{{.Status}}' | grep -q "Up"; then
  echo "[PORTAINER] ✅ Server running"
else
  echo "[PORTAINER] ❌ Server failed to start"
  docker logs portainer --tail 20
  exit 1
fi
REMOTE

log "✅ Phase 1 complete"

# --- Phase 2: Deploy agents on VPS fleet ---
log ""
log "Phase 2: Deploying agents on VPS fleet..."

deploy_agent() {
  local name="$1" host="$2"
  log "  Deploying agent on $name ($host)..."
  ssh -i "$SSH_KEY" -o ConnectTimeout=10 "$host" bash -s "$PORTAINER_SERVER_IP" <<'AGENT_EOF' || { log "  ⚠️  $name: failed (skipped)"; return 0; }
set -euo pipefail
SERVER_IP="$1"
docker rm -f portainer-agent 2>/dev/null || true
docker run -d \
  --name portainer-agent \
  --restart unless-stopped \
  -p 9001:9001 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /var/lib/docker/volumes:/var/lib/docker/volumes \
  portainer/agent:2.25.1
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow from "$SERVER_IP" to any port 9001 comment "Portainer agent" 2>/dev/null || true
  sudo ufw deny 9001 comment "Block public agent access" 2>/dev/null || true
fi
echo "[AGENT] ✅ agent running"
AGENT_EOF
}

deploy_agent "kong"        "debian@51.83.45.13"
deploy_agent "gravitee"    "debian@54.36.209.237"
deploy_agent "n8n"         "debian@51.254.139.205"
deploy_agent "infisical"   "debian@213.199.45.108"
deploy_agent "webmethods"  "debian@51.255.201.17"

log "  spare-gra-vps: local environment (Docker socket already mounted)"

log ""
log "✅ Phase 2 complete — all agents deployed"
log ""
log "Next steps:"
log "  1. Open https://portainer.gostoa.dev and set admin password"
log "  2. Add environments: Settings → Environments → Add → Agent"
log "     - kong:       51.83.45.13:9001"
log "     - gravitee:   54.36.209.237:9001"
log "     - n8n:        51.254.139.205:9001"
log "     - infisical:  213.199.45.108:9001"
log "     - webmethods: 51.255.201.17:9001"
log "  3. Add Cloudflare Access policy for portainer.gostoa.dev"
log "  4. Register in Netbox + Uptime Kuma"
