# Vault Agent — VPS Secret Management

Deploys HashiCorp Vault Agent as a systemd daemon on each VPS.
Agent auto-authenticates via AppRole, renders secret templates to `/opt/secrets/*.env`,
and restarts Docker services on secret change.

## Prerequisites

1. **Vault operational** (Phase 0 — CAB-1796)
2. **Secrets migrated** (Phase 1 — CAB-1797)
3. **VAULT_TOKEN** set (admin token for AppRole credential generation)

## VPS Matrix

| VPS | IP | AppRole | Templates | Docker services |
|-----|-----|---------|-----------|----------------|
| n8n/Netbox | 51.254.139.205 | `vps-n8n` | n8n, netbox, pocketbase | 3 compose stacks |
| Kong | 51.83.45.13 | `vps-kong` | kong | 1 compose stack |
| Gravitee | 54.36.209.237 | `vps-gravitee` | gravitee | 1 compose stack |
| webMethods | 51.255.201.17 | `vps-webmethods` | webmethods | 1 compose stack |
| HEGEMON (5x) | Contabo | `vps-hegemon` | in-memory (vault-loader.sh) | hegemon-agent |

## Deploy — Standard VPS

```bash
export VAULT_TOKEN="<admin-token>"
export VAULT_ADDR="https://hcvault.gostoa.dev"

# n8n VPS (golden template — deploy first)
./deploy.sh 51.254.139.205 vps-n8n n8n netbox pocketbase

# Gateway VPS
./deploy.sh 51.83.45.13 vps-kong kong
./deploy.sh 54.36.209.237 vps-gravitee gravitee
./deploy.sh 51.255.201.17 vps-webmethods webmethods
```

## Deploy — HEGEMON Workers

HEGEMON uses in-memory secrets (no file on disk). `vault-loader.sh` replaces `infisical-loader.sh`.

```bash
export VAULT_TOKEN="<admin-token>"

# Single worker
./deploy-hegemon.sh 62.171.178.49

# All 5 workers
./deploy-hegemon.sh all
```

## How It Works

### Standard VPS (systemd daemon)
```
Vault Agent (systemd)
  → AppRole auto-auth (role-id + secret-id on disk)
  → Renders templates: /etc/vault-agent/templates/*.env.tpl
  → Output: /opt/secrets/*.env (0600 perms)
  → On change: docker compose restart <service>
```

### HEGEMON Workers (shell loader)
```
hegemon-start.sh
  → source ~/.env.hegemon (fallback values)
  → source vault-loader.sh
    → AppRole login (role-id + secret-id from ~/.hegemon/)
    → Fetch secrets via Vault HTTP API
    → Export to env vars (memory only)
    → Unset token
```

## Verification

```bash
# Standard VPS — check agent status
ssh -i ~/.ssh/id_ed25519_stoa debian@<ip> 'systemctl status vault-agent'
ssh -i ~/.ssh/id_ed25519_stoa debian@<ip> 'ls -la /opt/secrets/'

# HEGEMON — verify secrets loaded
ssh -i ~/.ssh/id_ed25519_stoa hegemon@<ip> 'source ~/.local/bin/vault-loader.sh && echo OK'

# Test rotation: change a secret in Vault, verify it propagates
# Standard VPS: agent polls every ~5min, restarts Docker on change
# HEGEMON: secrets refresh on next shell/service restart
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `vault-agent: FAILED` | `journalctl -u vault-agent --no-pager -n 50` |
| Template not rendered | Check Vault connectivity: `curl -sf https://hcvault.gostoa.dev/v1/sys/health` |
| Auth failed | Verify role-id/secret-id: `cat /etc/vault-agent/role-id` |
| Docker not restarting | Check compose path in config.hcl matches actual location |
| HEGEMON secrets empty | `source ~/.local/bin/vault-loader.sh` manually, check stderr |
