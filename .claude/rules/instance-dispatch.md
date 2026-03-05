---
globs: ".github/workflows/claude-*,scripts/ai-ops/n8n-*"
---

# Instance Dispatch — Parallel tmux Mapping

## Instance Mapping

| Instance Label | Components | Pane | Scope | Commit Prefix |
|---|---|---|---|---|
| `instance:backend` | cp-api, operator, infra, docs | 2 (BACKEND) | `control-plane-api/`, `charts/`, `k8s/`, `stoa-docs` | `feat(api):`, `chore(infra):` |
| `instance:frontend` | cp-ui, portal, shared | 3 (FRONTEND) | `control-plane-ui/`, `portal/`, `shared/` | `feat(ui):`, `feat(portal):` |
| `instance:auth` | keycloak, IAM, OAuth | 4 (AUTH) | `keycloak/`, OAuth configs | `feat(auth):` |
| `instance:mcp` | stoa-gateway | 5 (MCP) | `stoa-gateway/` | `feat(gateway):` |
| `instance:qa` | e2e, cross-component tests | 6 (QA) | `e2e/` (read-only on rest) | `test(e2e):` |

## Tagging Rules

Auto-tagged by `/decompose`, `/generate-backlog`, `/council`, CI pipeline. Cross-component: lead instance label (most LOC) + `depends:instance:<other>` in description. Path detection: `control-plane-api/**`→backend, `control-plane-ui/**`→frontend, `stoa-gateway/**`→mcp, `e2e/**`→qa, `keycloak/**`→auth.

## Permission Enforcement

Two layers: PreToolUse hook (`pre-instance-scope.sh`) + instance settings (`.claude/instances/<role>.json`). Usage: `export STOA_INSTANCE=backend && claude` (or automatic via `stoa-parallel`).

### Deny Matrix

| Instance | Denied Paths (Edit/Write) | Denied Commands |
|----------|--------------------------|-----------------|
| backend | `/portal/`, `/stoa-gateway/src/`, `/control-plane-ui/src/`, `/e2e/` | `rm -rf`, `sudo` |
| frontend | `/control-plane-api/src/`, `/stoa-gateway/`, `/e2e/`, `/charts/`, `/k8s/` | `rm -rf`, `sudo`, `pytest`, `cargo`, `alembic` |
| auth | `/portal/src/`, `/stoa-gateway/src/`, `/control-plane-ui/src/`, `/e2e/` | `rm -rf`, `sudo`, `npm`, `cargo`, `pytest`, `alembic` |
| mcp | `/control-plane-ui/`, `/portal/`, `/e2e/`, `/control-plane-api/src/` | `rm -rf`, `sudo`, `npm`, `pytest`, `alembic` |
| qa | `/control-plane-api/src/`, `/control-plane-ui/src/`, `/portal/src/`, `/stoa-gateway/src/`, `/charts/`, `/k8s/` | `rm -rf`, `sudo`, `cargo`, `alembic`, `terraform` |

## Slack Session Notifications

Stop hook sends Slack notification with instance role, branch, last 3 commits, PR status, uncommitted count. Requires `SLACK_WEBHOOK_URL`.

## tmux Layout (`stoa-parallel`)

7 panes in single window: ORCHESTRE(0), MONITOR(1), BACKEND(2), FRONTEND(3), AUTH(4), MCP(5), QA(6). Navigation: `Ctrl+B q` (jump), `Ctrl+B z` (zoom), `Ctrl+B o` (cycle). Pane borders show static role labels.

### ORCHESTRE Rules (Pane 0)

Dispatcher only — never implements. Does: read state, dispatch via `stoa-dispatch`, monitor via `heg-state remote-ls`, verify CD, update state files, run `/sync-plan`, `/fill-cycle`, `/council`, `/verify-mega`. Never: create branches, edit code, run tests, create PRs. Context: `/compact` at 10 turns or 40%, `/clear` between cycles, stop at 60%.

### tmux Gotchas

`no space for new pane` → `tmux new-session -x 220 -y 60`. PATH missing → explicit `/opt/homebrew/bin` export. `send-keys` race → sleep 2 after PATH, 0.3 between commands. Setup wizard → pre-populate `.claude.json`.

## Shared State via PocketBase (CAB-1513)

`state.gostoa.dev` replaces `.claude/claims/*.json`. Protocol: `heg-state start/step/done/remote-ls`. Fallback: local SQLite if PocketBase unreachable.

### Council Gate (MANDATORY — post-C11 audit)

`stoa-dispatch` queries Linear for `council:ticket-go|fix` before dispatching. No label → BLOCKED. Bypass: `--force` flag. `LINEAR_API_KEY` required (graceful degradation without it).

### Linear Auto-Status

Every instance: ticket start → In Progress, PR merge → Done + comment, block → Blocked + comment.

## Billing Split

All panes on API key (`ANTHROPIC_API_KEY`). `CLAUDE_CONFIG_DIR=/tmp/claude-api-config-clean` for API panes — no `.credentials.json` so Max credentials are invisible. Pre-populated `.claude.json` skips setup wizard. API key resolution: explicit flag → env var → Infisical → all-Max fallback.

### Billing Gotchas

All on Max? → Use `CLAUDE_CONFIG_DIR`. Stuck in wizard? → Pre-populate `.claude.json`. Logout breaks all? → Never logout, use config dir isolation.
