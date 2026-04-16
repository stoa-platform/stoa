<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
description: stoactl CLI usage — prefer stoactl over curl/scripts for platform operations
globs: "stoa-go/**,scripts/ops/**,control-plane-api/src/routers/**"
---

# stoactl CLI — Prefer Over curl/scripts

## Golden Rule

**Use `stoactl` for any operation it supports.** Do NOT use curl, httpx, or bash scripts when stoactl has a command for it.

## Binary Location

- Installed: `/opt/homebrew/bin/stoactl` or `stoa-go/bin/stoactl` (local build)
- Build: `cd stoa-go && go build -o bin/stoactl ./cmd/stoactl/`
- If `stoactl` not in PATH, use `stoa-go/bin/stoactl` directly

## Available Commands (Phase 0+1+3)

| Operation | stoactl command | Replaces |
|-----------|----------------|----------|
| Catalog drift detection | `stoactl catalog sync --dry-run` | `ops/catalog-sync.sh`, `reconcile-catalog.py` |
| Catalog reconciliation | `stoactl catalog sync --apply` | `ops/reconcile-catalog.py --apply` |
| Audit log export | `stoactl audit export --tenant X --since 7d` | `curl /v1/audit` |
| Audit compliance CSV | `stoactl audit export --tenant X --since 30d --output csv` | Manual API + jq |
| API listing | `stoactl get apis` | `curl /v1/tenants/{t}/apis` |
| Apply resource | `stoactl apply -f <file>` | `curl -X POST /v1/...` |
| Gateway health | `stoactl gateway health` | `curl /health` |
| MCP tools list | `stoactl mcp list-tools` | `curl /mcp/tools/list` |
| Bridge OpenAPI→MCP | `stoactl bridge -f openapi.yaml` | Manual conversion |
| Auth status | `stoactl auth status` | `curl /v1/auth/me` |
| System diagnostics | `stoactl doctor` | Manual checks |
| Consumer listing | `stoactl get consumers` | `curl /v1/consumers/{t}` |
| Contract listing | `stoactl get contracts` | `curl /v1/tenants/{t}/contracts` |
| Service account listing | `stoactl get service-accounts` | `curl /v1/service-accounts` |
| Environment listing | `stoactl get environments` | `curl /v1/environments` |
| Plan listing | `stoactl get plans` | `curl /v1/plans/{t}` |
| Webhook listing | `stoactl get webhooks` | `curl /v1/tenants/{t}/webhooks` |
| Delete any resource | `stoactl delete <kind> <id>` | `curl -X DELETE /v1/...` |

### Apply Supported Kinds (Phase 3)

`stoactl apply -f` supports: **API**, **Tenant**, **Gateway**, **Subscription**, **Consumer**, **Contract**, **MCPServer**, **ServiceAccount**, **Plan**, **Webhook**.

### Get Supported Resources (Phase 3)

`stoactl get` supports: **apis**, **tenants**, **subscriptions**, **gateways**, **consumers**, **contracts**, **service-accounts**, **environments**, **plans**, **webhooks**.

### Delete Supported Resources (Phase 3)

`stoactl delete` supports: **api**, **tenant**, **gateway**, **subscription**, **consumer**, **contract**, **service-account**, **plan**, **webhook**.

## When to Use in AI Factory

| Context | Use stoactl | NOT |
|---------|------------|-----|
| Session startup — check catalog drift | `stoactl catalog sync --dry-run` | `bash ops/catalog-sync.sh` |
| Post-merge — verify API state | `stoactl get apis --output json` | `curl -H "Auth: ..." /v1/...` |
| Audit trail for compliance | `stoactl audit export --redact-pii` | `curl /v1/audit \| jq` |
| Debug gateway issues | `stoactl gateway health` | `curl /health` |
| E2E audit — check MCP tools | `stoactl mcp list-tools` | `curl /mcp/tools/list` |

## Flags Convention

- `--output json|yaml|table|csv` — all commands support output format
- `--admin` — use service account context (for admin-only endpoints)
- `--redact-pii` — default true on `audit export` (masks emails/IPs)
- `--dry-run` — preview changes without applying (catalog sync)
- `--tenant` — scope to a specific tenant

## CLI-First Context Reference

For complete API surface (all commands, resource schemas, endpoint map):
→ Read `.claude/context/cli-reference.md` (auto-generated from stoactl + JSON Schemas)

Regenerate after changes: `scripts/generate-cli-context.sh`

## Phase 2+ (coming after adoption gate — CAB-2033, due 2026-04-23)

Reserved commands (not yet available):
- `stoactl trace query` — distributed trace analysis
- `stoactl usage report` — billing/usage metrics
- `stoactl quota set` — rate limit management
- `stoactl gateway route add` — route registration
