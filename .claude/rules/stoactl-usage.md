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

## Available Commands (Phase 0+1)

| Operation | stoactl command | Replaces |
|-----------|----------------|----------|
| Catalog drift detection | `stoactl catalog sync --dry-run` | `ops/catalog-sync.sh`, `reconcile-catalog.py` |
| Catalog reconciliation | `stoactl catalog sync --apply` | `ops/reconcile-catalog.py --apply` |
| Audit log export | `stoactl audit export --tenant X --since 7d` | `curl /v1/audit` |
| Audit compliance CSV | `stoactl audit export --tenant X --since 30d --output csv` | Manual API + jq |
| API listing | `stoactl get apis` | `curl /v1/tenants/{t}/apis` |
| Apply resource | `stoactl apply -f api.yaml` | `curl -X POST /v1/...` |
| Gateway health | `stoactl gateway health` | `curl /health` |
| MCP tools list | `stoactl mcp list-tools` | `curl /mcp/tools/list` |
| Bridge OpenAPI→MCP | `stoactl bridge -f openapi.yaml` | Manual conversion |
| Auth status | `stoactl auth status` | `curl /v1/auth/me` |
| System diagnostics | `stoactl doctor` | Manual checks |

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

## Phase 2+ (coming after adoption gate — CAB-2033, due 2026-04-23)

Reserved commands (not yet available):
- `stoactl trace query` — distributed trace analysis
- `stoactl usage report` — billing/usage metrics
- `stoactl quota set` — rate limit management
- `stoactl gateway route add` — route registration
