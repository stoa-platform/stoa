# n8n secrets — rendered by Vault Agent
# Source: Vault KV v2 at stoa/vps/n8n + stoa/shared/slack
{{ with secret "stoa/data/vps/n8n" }}
POSTGRES_PASSWORD={{ .Data.data.POSTGRES_PASSWORD }}
N8N_ENCRYPTION_KEY={{ .Data.data.N8N_ENCRYPTION_KEY }}
{{ end }}
{{ with secret "stoa/data/shared/slack" }}
APPROVE_HMAC_SECRET={{ .Data.data.APPROVE_HMAC_SECRET }}
SLACK_SIGNING_SECRET={{ .Data.data.SLACK_SIGNING_SECRET }}
SLACK_BOT_TOKEN={{ .Data.data.SLACK_BOT_TOKEN }}
SLACK_CHANNEL_ID={{ .Data.data.SLACK_CHANNEL_ID }}
SLACK_ALLOWED_USERS={{ .Data.data.SLACK_ALLOWED_USERS }}
SLACK_ADMIN_USERS={{ .Data.data.SLACK_ADMIN_USERS }}
{{ end }}
