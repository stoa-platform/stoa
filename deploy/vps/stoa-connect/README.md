# STOA Connect — VPS Deployment

Deploys the `stoa-connect` agent as a systemd service on VPS instances running third-party gateways (Kong, Gravitee, webMethods).

## What stoa-connect does

- Registers the VPS gateway instance with the STOA Control Plane
- Sends heartbeats every 30s to maintain ONLINE status
- Appears in Console UI with "Connect" mode badge

## Prerequisites

1. **Vault secret** at `stoa/shared/stoa-connect`:
   ```bash
   vault kv put stoa/shared/stoa-connect \
     STOA_CONTROL_PLANE_URL=https://api.gostoa.dev \
     STOA_GATEWAY_API_KEY=<key-from-infisical>
   ```

2. **Vault Agent** deployed with `stoa-connect.env.tpl` template:
   ```bash
   cd deploy/vps/vault-agent
   ./deploy.sh <vps-ip> <vps-name> <instance> stoa-connect
   ```

3. **SSH access** to VPS (key: `~/.ssh/id_ed25519_stoa`)

## Deploy

```bash
# Kong VPS
./deploy.sh 51.83.45.13 kong-vps production

# Gravitee VPS
./deploy.sh 54.36.209.237 gravitee-vps production

# webMethods VPS
./deploy.sh 51.255.201.17 webmethods-vps production
```

## Verify

```bash
# On VPS
systemctl status stoa-connect
curl localhost:8090/health

# From Control Plane
curl -sH "Authorization: Bearer ${TOKEN}" \
  "https://api.gostoa.dev/v1/admin/gateways" \
  | jq '[.items[] | select(.mode == "connect")] | length'
# Expected: 3

# Console UI
# Navigate to /gateways → see Connect instances with teal badges
# Navigate to /gateways/modes → see Connect card
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `stoa-connect.env not found` | Deploy Vault Agent with stoa-connect template first |
| Service crashes on start | Check `journalctl -u stoa-connect -f` for errors |
| Registers as `edge-mcp` | API fix needed (PR #1741) — `_normalize_mode` must handle "connect" |
| No heartbeat in Console | Check VPS can reach `api.gostoa.dev` (firewall, DNS) |
