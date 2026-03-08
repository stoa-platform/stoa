# n8n API — Full Reference

> Extracted from `.claude/rules/n8n-api.md` (rules diet). Essential gotchas and workflows remain in the rule file.

## Authentication

```bash
eval $(infisical-token)
N8N_API_KEY=$(curl -s "https://vault.gostoa.dev/api/v3/secrets/raw/N8N_API_KEY?workspaceId=$INFISICAL_PROJECT_ID&environment=prod&secretPath=/n8n" \
  -H "Authorization: Bearer $INFISICAL_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['secret']['secretValue'])")
```

## Workflow CRUD

```bash
# List
curl -s https://n8n.gostoa.dev/api/v1/workflows -H "X-N8N-API-KEY: $N8N_API_KEY"

# Import (strip tags/meta)
python3 -c "
import json, sys
wf = json.load(open('scripts/ai-ops/n8n-my-workflow.json'))
clean = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
json.dump(clean, sys.stdout)
" | curl -s -X POST https://n8n.gostoa.dev/api/v1/workflows \
  -H "X-N8N-API-KEY: $N8N_API_KEY" -H "Content-Type: application/json" -d @-

# Update (active is READ-ONLY)
curl -s -X PUT "https://n8n.gostoa.dev/api/v1/workflows/$WF_ID" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" -H "Content-Type: application/json" -d "$WORKFLOW_JSON"

# Activate / Deactivate
curl -s -X POST "https://n8n.gostoa.dev/api/v1/workflows/$WF_ID/activate" -H "X-N8N-API-KEY: $N8N_API_KEY"
curl -s -X POST "https://n8n.gostoa.dev/api/v1/workflows/$WF_ID/deactivate" -H "X-N8N-API-KEY: $N8N_API_KEY"

# Delete
curl -s -X DELETE "https://n8n.gostoa.dev/api/v1/workflows/$WF_ID" -H "X-N8N-API-KEY: $N8N_API_KEY"

# Test webhook
curl -s -X POST "https://n8n.gostoa.dev/webhook/<path>" -H "Content-Type: application/json" -d '{"test": true}'
```

## Env Vars in n8n Docker

Set in `~/n8n/.env` on VPS. **Must `down` + `up -d`** (restart won't reload).

```bash
sshpass -p "$VPS_PASS" ssh debian@<N8N_VPS_IP>
echo 'MY_NEW_VAR=value' >> ~/n8n/.env
cd ~/n8n && docker compose down n8n && docker compose up -d n8n
```

| Variable | Purpose | Source |
|----------|---------|--------|
| `GITHUB_PAT` | GitHub API | Infisical `/n8n/GITHUB_PAT` |
| `APPROVE_HMAC_SECRET` | Slack button signature | Infisical |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook | Infisical |
| `SLACK_SIGNING_SECRET` | Slack request verification | Infisical |
| `SLACK_BOT_TOKEN` | Slack Bot API | Infisical |
| `SLACK_CHANNEL_ID` | Target channel | Infisical |
| `SLACK_ALLOWED_USERS` | Tier 2 users | Infisical |
| `SLACK_ADMIN_USERS` | Tier 1 users | Infisical |

## Workflow JSON Convention

Files: `scripts/ai-ops/n8n-*.json`. Required fields: `name`, `nodes`, `connections`, `settings`.

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
  "typeVersion": 2
}
```

### Code Node Pattern

```json
{
  "parameters": {
    "jsCode": "const https = require('https');\nconst secret = $env.MY_SECRET || '';\nreturn [{ json: { status: 'ok' } }];"
  },
  "type": "n8n-nodes-base.code",
  "typeVersion": 2
}
```

Required `.env` for Code nodes: `NODE_FUNCTION_ALLOW_BUILTIN=crypto,https,url,buffer`, `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.
