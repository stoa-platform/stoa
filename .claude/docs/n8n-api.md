<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
globs: "scripts/ai-ops/n8n-*,.github/workflows/claude-*"
---

# n8n API — Programmatic Workflow Management

## Instance

| Field | Value |
|-------|-------|
| URL | `https://n8n.gostoa.dev` |
| API Base | `https://n8n.gostoa.dev/api/v1` |
| Auth | `X-N8N-API-KEY` header (Infisical `/n8n/N8N_API_KEY`) |

## Key Gotchas

| Issue | Fix |
|-------|-----|
| Extra fields on import | Strip to `name`, `nodes`, `connections`, `settings` only |
| `active` on PUT | Remove from PUT body; use `/activate` endpoint |
| `responseMode` mismatch | Use `"responseNode"` when workflow has `respondToWebhook` node |
| Env var not available | Must be in Docker `.env`, then `docker compose down && up -d` |
| `docker compose restart` | Does NOT reload `.env` — must `down` + `up -d` |
| Tags on import | Strip `tags` array (API expects tag IDs, not names) |

## Active Workflows

| Name | Webhook Path | Purpose |
|------|-------------|---------|
| Approve Ticket Relay | `/webhook/approve-ticket` | Slack → GitHub `/go` |
| Linear → Council | — | Linear status → GHA dispatch |
| Merge PR Relay | `/webhook/merge-pr` | Slack → GitHub PR merge |
| Slack Interactive | `/webhook/slack-interactive` | Slack button payloads |
| /stoa Slash Command | `/webhook/stoa-slash-command` | `/stoa` commands |
| Blog Publish | `/webhook/blog-publish` | GHA → Google Indexing |

## Reference

Full details (CRUD examples, env vars, JSON conventions, node patterns):
→ `docs/ai-ops/n8n-reference.md`
