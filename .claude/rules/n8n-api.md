---
globs: scripts/ai-ops/n8n-*, .github/workflows/*n8n*, .github/workflows/*linear*, .github/workflows/*autopilot*
---

# n8n API — Programmatic Workflow Management

## Instance

| Field | Value |
|-------|-------|
| URL | `https://n8n.gostoa.dev` |
| API Base | `https://n8n.gostoa.dev/api/v1` |
| VPS | `51.254.139.205` (OVH Debian 12, shared with Healthchecks) |
| SSH | `sshpass -p "$VPS_PASS" ssh debian@51.254.139.205` |
| Path | `~/n8n/` (docker-compose.yml + .env) |
| API Key | Infisical `/n8n/N8N_API_KEY` |

## Authentication

```bash
# Get API key from Infisical
eval $(infisical-token)
N8N_API_KEY=$(curl -s "https://vault.gostoa.dev/api/v3/secrets/raw/N8N_API_KEY?workspaceId=97972ffc-990b-4d28-9c4d-0664d217f03b&environment=prod&secretPath=/n8n" \
  -H "Authorization: Bearer $INFISICAL_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['secret']['secretValue'])")

# All API calls use X-N8N-API-KEY header
curl -s https://n8n.gostoa.dev/api/v1/workflows \
  -H "X-N8N-API-KEY: $N8N_API_KEY"
```

## Workflow CRUD

### List workflows
```bash
curl -s https://n8n.gostoa.dev/api/v1/workflows \
  -H "X-N8N-API-KEY: $N8N_API_KEY" | python3 -m json.tool
```

### Import (create) a workflow
```bash
# CRITICAL: strip tags, meta, and any extra fields — n8n rejects unknown properties
python3 -c "
import json, sys
wf = json.load(open('scripts/ai-ops/n8n-my-workflow.json'))
clean = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
json.dump(clean, sys.stdout)
" | curl -s -X POST https://n8n.gostoa.dev/api/v1/workflows \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d @-
```

### Update a workflow
```bash
# active field is READ-ONLY on PUT — omit it or the API rejects
# Must send full body (name, nodes, connections, settings)
curl -s -X PUT "https://n8n.gostoa.dev/api/v1/workflows/$WF_ID" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$WORKFLOW_JSON"
```

### Activate / Deactivate
```bash
curl -s -X POST "https://n8n.gostoa.dev/api/v1/workflows/$WF_ID/activate" \
  -H "X-N8N-API-KEY: $N8N_API_KEY"

curl -s -X POST "https://n8n.gostoa.dev/api/v1/workflows/$WF_ID/deactivate" \
  -H "X-N8N-API-KEY: $N8N_API_KEY"
```

### Delete
```bash
curl -s -X DELETE "https://n8n.gostoa.dev/api/v1/workflows/$WF_ID" \
  -H "X-N8N-API-KEY: $N8N_API_KEY"
```

## Test a webhook workflow
```bash
curl -s -X POST "https://n8n.gostoa.dev/webhook/<path>" \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

## Gotchas

| Issue | Symptom | Fix |
|-------|---------|-----|
| Extra fields on import | `request/body must NOT have additional properties` | Strip to `name`, `nodes`, `connections`, `settings` only |
| `active` on PUT | `request/body/active is read-only` | Remove `active` from PUT body; use `/activate` endpoint |
| PATCH not supported | `405 Method Not Allowed` | Use PUT (full body) for updates |
| `responseMode` mismatch | `Unused Respond to Webhook node` (code 0 error) | If workflow has a `respondToWebhook` node, webhook must use `"responseMode": "responseNode"` (not `"lastNode"`) |
| Env var not available | `$env.VAR` returns empty in Code node | Var must be in Docker container `.env`, not just Infisical. Then full recreate: `docker compose down n8n && docker compose up -d n8n` |
| `docker compose restart` | New env vars not picked up | Restart does NOT reload `.env`. Must `down` + `up -d` for full recreate |
| `NODE_FUNCTION_ALLOW_BUILTIN` | `require('https')` fails in Code node | Set `NODE_FUNCTION_ALLOW_BUILTIN=crypto,https,url,buffer` in `.env` |
| `$env` blocked | `Environment data access blocked` | Set `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` in `.env` |
| Tags on import | n8n API rejects `tags` array (expects tag IDs, not names) | Strip `tags` from import payload |

## Env Vars in n8n Docker

Env vars are set in `~/n8n/.env` on the VPS. To add a new one:

```bash
# 1. SSH into VPS
sshpass -p "$VPS_PASS" ssh debian@51.254.139.205

# 2. Add to .env
echo 'MY_NEW_VAR=value' >> ~/n8n/.env

# 3. Full recreate (restart won't pick up new vars)
cd ~/n8n && docker compose down n8n && docker compose up -d n8n

# 4. Verify
docker compose exec n8n env | grep MY_NEW_VAR
```

### Current env vars (in .env)
| Variable | Purpose | Source |
|----------|---------|--------|
| `GITHUB_PAT` | GitHub API (dispatch, PR) | Infisical `/n8n/GITHUB_PAT` |
| `APPROVE_HMAC_SECRET` | Slack button signature | Infisical `/n8n/APPROVE_HMAC_SECRET` |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook | Infisical `/n8n/SLACK_WEBHOOK_URL` |
| `SLACK_SIGNING_SECRET` | Slack request verification | Infisical `/n8n/SLACK_SIGNING_SECRET` |
| `SLACK_BOT_TOKEN` | Slack Bot API (reactions, threads) | Infisical `/n8n/SLACK_BOT_TOKEN` |
| `SLACK_CHANNEL_ID` | Target Slack channel | Infisical `/n8n/SLACK_CHANNEL_ID` |
| `SLACK_ALLOWED_USERS` | Tier 2 users (approve/merge) | Infisical `/n8n/SLACK_ALLOWED_USERS` |
| `SLACK_ADMIN_USERS` | Tier 1 users (scan/implement) | Infisical `/n8n/SLACK_ADMIN_USERS` |

## Workflow JSON Convention

Workflow files live in `scripts/ai-ops/n8n-*.json`. Each file includes:
- `name`: display name in n8n UI
- `nodes`: array of node definitions
- `connections`: node-to-node wiring
- `settings`: `{ "executionOrder": "v1" }`
- `meta.notes`: setup instructions + required env vars (for human reference, stripped on import)
- `tags`: category tags (for human reference, stripped on import)

### Webhook Node Pattern
```json
{
  "parameters": {
    "httpMethod": "POST",
    "path": "my-endpoint",
    "responseMode": "responseNode",
    "options": {}
  },
  "type": "n8n-nodes-base.webhook",
  "typeVersion": 2,
  "webhookId": "my-endpoint"
}
```

Always use `"responseMode": "responseNode"` when the workflow has a `respondToWebhook` node downstream.

### Code Node Pattern (with env + HTTP)
```json
{
  "parameters": {
    "jsCode": "const https = require('https');\nconst secret = $env.MY_SECRET || '';\n// ... logic ...\nreturn [{ json: { status: 'ok' } }];"
  },
  "type": "n8n-nodes-base.code",
  "typeVersion": 2
}
```

## Active Workflows

| ID | Name | Webhook Path | Purpose |
|----|------|-------------|---------|
| `0KPautNojGBEiPCT` | Approve Ticket Relay | `/webhook/approve-ticket` | Slack button → GitHub `/go` comment |
| `6P1RIqDibRRl0lJd` | Linear → Council | — | Linear status change → GHA dispatch |
| `gbBuc0CwbE544aGp` | Merge PR Relay | `/webhook/merge-pr` | Slack button → GitHub PR merge |
| `mpgpE9Uf3h4UDN1H` | Slack Interactive | `/webhook/slack-interactive` | Slack button payloads |
| `XTZFFQCm8dsZqT3n` | /stoa Slash Command | `/webhook/stoa-slash-command` | `/stoa` Slack commands |
| `NAB5YtLae2P5b3JS` | Blog Publish | `/webhook/blog-publish` | GHA → Google Indexing + Slack |
