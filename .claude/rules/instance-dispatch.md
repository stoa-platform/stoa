---
globs:
  - ".claude/**"
  - "scripts/**"
---

# Instance Dispatch — Parallel tmux Mapping

## Overview

Every ticket on Linear gets an `instance:*` label that maps to a parallel tmux window.
When `stoa-parallel` launches, each Claude instance filters Linear for its own tickets.

## Instance Mapping

| Instance Label | Components | tmux Window | Scope | Commit Prefix |
|---|---|---|---|---|
| `instance:backend` | cp-api, operator, infra, docs | Window 2 (BACKEND) | `control-plane-api/`, `charts/`, `k8s/`, `stoa-docs` | `feat(api):`, `chore(infra):` |
| `instance:frontend` | cp-ui, portal, shared | Window 3 (FRONTEND) | `control-plane-ui/`, `portal/`, `shared/` | `feat(ui):`, `feat(portal):` |
| `instance:auth` | keycloak, IAM, OAuth | Window 4 (AUTH) | `keycloak/`, OAuth configs | `feat(auth):`, `fix(auth):` |
| `instance:mcp` | stoa-gateway | Window 5 (MCP) | `stoa-gateway/` | `feat(gateway):`, `fix(gateway):` |
| `instance:qa` | e2e, cross-component tests | Window 6 (QA) | `e2e/` (read-only on rest) | `test(e2e):`, `test(api):` |

## Label IDs (cached)

| Label | ID |
|-------|-----|
| `instance:backend` | `b60c32eb-3374-4a53-a487-b409bfed2d61` |
| `instance:frontend` | `e9434a2f-f313-4223-a042-598185718c7b` |
| `instance:auth` | `c4bb2546-7bbc-45d9-b5ab-384fd7065d48` |
| `instance:mcp` | `19497340-8712-45d0-8728-a77c96c592a7` |
| `instance:qa` | `00ba65ee-81e3-40e8-b2d2-38f340617b2f` |

## Tagging Rules

### When to tag

| Action | Who Tags | How |
|--------|----------|-----|
| `/decompose` creates sub-issues | Skill auto-tags | Component → instance mapping |
| `/generate-backlog --create` | Skill auto-tags | Lead component → instance |
| `/council` creates ticket | Skill auto-tags | Detected component → instance |
| `/fill-cycle` promotes to cycle | Preserves existing label | No change |
| CI pipeline (L1/L3) creates ticket | Workflow tags | `component` field in dispatch payload |
| Manual ticket creation | Human tags | Pick from `instance:*` dropdown |

### Cross-component tickets

If a ticket touches multiple instances:
1. Assign the **lead instance** label (most LOC impact)
2. Add `depends:instance:<other>` in the ticket description
3. The lead instance does the work; other instances verify during QA

### Single-component detection

| Primary Path | Instance |
|---|---|
| `control-plane-api/**` | `instance:backend` |
| `stoa-operator/**` | `instance:backend` |
| `charts/**`, `k8s/**` | `instance:backend` |
| `control-plane-ui/**` | `instance:frontend` |
| `portal/**` | `instance:frontend` |
| `shared/**` | `instance:frontend` |
| `keycloak/**` | `instance:auth` |
| `stoa-gateway/**` | `instance:mcp` |
| `e2e/**` | `instance:qa` |
| `stoa-docs` (separate repo) | `instance:backend` |

## Permission Enforcement (CAB-1481)

Each instance has a deny list preventing cross-scope file edits and unauthorized commands.

### Mechanism

Two layers of enforcement:
1. **PreToolUse hook** (`pre-instance-scope.sh`) — reads `STOA_INSTANCE` env var, blocks denied operations at runtime
2. **Instance settings files** (`.claude/instances/<role>.json`) — define deny rules per role

### Usage

```bash
# Standalone session (any terminal)
export STOA_INSTANCE=backend && claude

# stoa-parallel (automatic per window)
stoa-parallel  # each window gets STOA_INSTANCE=<role>

# Clear instance scope
unset STOA_INSTANCE
```

### Deny Matrix

| Instance | Denied Paths (Edit/Write) | Denied Commands |
|----------|--------------------------|-----------------|
| backend | `/portal/`, `/stoa-gateway/src/`, `/control-plane-ui/src/`, `/e2e/` | `rm -rf`, `sudo` |
| frontend | `/control-plane-api/src/`, `/stoa-gateway/`, `/e2e/`, `/charts/`, `/k8s/` | `rm -rf`, `sudo`, `pytest`, `cargo`, `alembic` |
| auth | `/portal/src/`, `/stoa-gateway/src/`, `/control-plane-ui/src/`, `/e2e/` | `rm -rf`, `sudo`, `npm`, `cargo`, `pytest`, `alembic` |
| mcp | `/control-plane-ui/`, `/portal/`, `/e2e/`, `/control-plane-api/src/` | `rm -rf`, `sudo`, `npm`, `pytest`, `alembic` |
| qa | `/control-plane-api/src/`, `/control-plane-ui/src/`, `/portal/src/`, `/stoa-gateway/src/`, `/charts/`, `/k8s/` | `rm -rf`, `sudo`, `cargo`, `alembic`, `terraform` |

### Files

| File | Purpose |
|------|---------|
| `.claude/instances/backend.json` | Backend instance deny rules |
| `.claude/instances/frontend.json` | Frontend instance deny rules |
| `.claude/instances/auth.json` | Auth instance deny rules |
| `.claude/instances/mcp.json` | MCP/Gateway instance deny rules |
| `.claude/instances/qa.json` | QA instance deny rules |
| `.claude/hooks/pre-instance-scope.sh` | PreToolUse hook enforcing scope |
| `.claude/hooks/stop-slack-notify.sh` | Stop hook sending Slack session summary |

## Slack Session Notifications

When `SLACK_WEBHOOK_URL` is set, each Claude session sends a Slack notification on Stop with:
- Instance role and branch name
- Last 3 commits
- Open PR status (if any)
- Uncommitted file count
- "Waiting for next instruction" footer

Set `SLACK_WEBHOOK_URL` in your shell profile or `.claude/settings.local.json` env section.

## tmux Layout (`stoa-parallel`)

```
Session: stoa — Single window "workspace" with 7 panes (tiled grid, all visible)
+------+------+------+------+
| 0    | 1    | 2    | 3    |
| ORCH | MON  | BACK | FRONT|
+------+------+------+------+
| 4    | 5    | 6    |
| AUTH | MCP  | QA   |
+------+------+------+

Pane 0: ORCHESTRE  (lead orchestrator, Max billing)
Pane 1: MONITOR    (htop + watchdog, no Claude)
Pane 2: BACKEND    (STOA_INSTANCE=backend, Max billing)
Pane 3: FRONTEND   (STOA_INSTANCE=frontend, API billing)
Pane 4: AUTH       (STOA_INSTANCE=auth, API billing)
Pane 5: MCP        (STOA_INSTANCE=mcp, API billing)
Pane 6: QA         (STOA_INSTANCE=qa, API billing)
```

Pane borders show role names via `pane-border-format` with nested `#{?#{==:#{pane_index},N},...}` conditionals — static labels immune to Claude Code title overrides.

Navigation: `Ctrl+B q` (show numbers + jump), `Ctrl+B z` (zoom toggle), `Ctrl+B o` (cycle).

### tmux Gotchas

| Issue | Cause | Fix |
|-------|-------|-----|
| `no space for new pane` | Detached session needs explicit size | Use `tmux new-session -x 220 -y 60` |
| Panes don't have Homebrew in PATH | tmux doesn't source `.zprofile` | Explicit `export PATH="/opt/homebrew/bin:..."` to all panes |
| `send-keys` race condition | Commands queued faster than shell processes | `sleep 2` after PATH export, `sleep 0.3` between env+claude |
| First-time setup wizard in API panes | `CLAUDE_CONFIG_DIR` points to fresh dir | Pre-populate `.claude.json` with onboarding flags |

Each Claude instance at startup:
- `STOA_INSTANCE` env var set via `export` -> hook enforces deny rules
- Session startup mechanism loads context automatically (memory.md, plan.md, CLAUDE.md)
- Role context loaded from `.claude/instances/<role>.local.md` (generated by stoa-parallel)
- Startup prompt includes: instance role, scope exclusif, max 5 tickets from Linear cycle
- Linear filter: `list_issues(labels: ['instance:<role>'], cycle: current)`

## Shared State via PocketBase (CAB-1513)

PocketBase (`state.gostoa.dev`) replaces `.claude/claims/*.json` as the shared state store for parallel instances.

### Protocol (every instance MUST follow)

| Action | Command | Effect |
|--------|---------|--------|
| **Start work** | `heg-state start --ticket CAB-XXXX --role <role> --branch feat/...` | Registers session + claims ticket in PocketBase |
| **Step progress** | `heg-state step CAB-XXXX pr-created --pr 578` | Updates step in PocketBase |
| **Complete** | `heg-state done CAB-XXXX` | Marks done in PocketBase + releases claim |
| **List sessions** | `heg-state remote-ls` | Shows all active sessions + claims (ORCHESTRE uses this) |

### Fallback

If PocketBase is unreachable (`state.gostoa.dev` down), `heg-state` falls back to local SQLite (`~/.hegemon/state.db`). All operations continue — remote sync resumes when connectivity returns.

### ORCHESTRE Visibility

ORCHESTRE polls `heg-state remote-ls` to see all instance states and dispatches via `stoa-dispatch`:
```bash
# See all active sessions + claims
heg-state remote-ls

# Send instruction to an instance
stoa-dispatch BACKEND "Travaille sur CAB-1350"
stoa-dispatch MCP "Quel est ton avancement ?"
```

### Linear Auto-Status (MANDATORY)

Every instance prompt includes:
- On ticket start: `linear.update_issue(id, state="In Progress")`
- On PR merge: `linear.update_issue(id, state="Done")` + `linear.create_comment(...)`
- On block: `linear.update_issue(id, state="Blocked")` + comment

## Billing Split (2 Max + 4 API)

### Default Allocation

| Pane | Role | Billing | Rationale |
|------|------|---------|-----------|
| 0 | ORCHESTRE | Max subscription | Lead orchestrator, full repo access |
| 2 | BACKEND | Max subscription | Heaviest workload (API + infra + tests) |
| 3 | FRONTEND | API key | UI work, lighter context |
| 4 | AUTH | API key | Narrow scope |
| 5 | MCP | API key | Gateway scope (was Max, moved to API after testing) |
| 6 | QA | API key | Read-heavy, write-light |

Override: `--max-panes=0,2,5` (comma-separated pane indices).

### How Billing Split Works (`CLAUDE_CONFIG_DIR`)

Claude Code always prefers Max subscription over `ANTHROPIC_API_KEY` env var when `~/.claude/.credentials.json` contains valid Max credentials. The ONLY way to force API billing is to prevent the instance from seeing Max credentials.

**Mechanism**: `CLAUDE_CONFIG_DIR` env var overrides the default `~/.claude/` config directory. API-billed panes get `CLAUDE_CONFIG_DIR=/tmp/claude-api-config` — a directory that:
1. Has `settings.json` + `settings.local.json` (permissions, model config)
2. Has `CLAUDE.md` (global instructions)
3. Has a symlink to `~/.claude/projects/` (session persistence)
4. Has a pre-populated `.claude.json` (onboarding complete, trust accepted, API key pre-approved)
5. Does **NOT** have `.credentials.json` — so Claude Code falls back to `ANTHROPIC_API_KEY`

Max-billed panes use the default `~/.claude/` directory (which has `.credentials.json` with Max auth).

### Pre-Populated `.claude.json` (Skip Setup Wizard)

Without `.claude.json`, Claude Code runs a 5-step interactive first-time setup wizard (theme → account type → API key → security notice → trust dialog). Navigating this via `tmux send-keys` is fragile. The script pre-populates `.claude.json` with:

```json
{
  "hasCompletedOnboarding": true,
  "lastOnboardingVersion": "2.1.59",
  "customApiKeyResponses": { "approved": ["<last-20-chars-of-key>"] },
  "projects": {
    "<each-workspace-dir>": { "hasTrustDialogAccepted": true }
  }
}
```

This skips the wizard entirely — instances go straight to the prompt.

### API Key Resolution Order

1. `--api-key=sk-ant-...` (explicit flag)
2. `ANTHROPIC_API_KEY` env var (from `.zshrc` or shell)
3. Infisical vault auto-fetch (`vault.gostoa.dev/prod/anthropic/ANTHROPIC_API_KEY`)
4. Fallback: all-Max mode (if no key available)

### Critical Gotchas

| Issue | Symptom | Root Cause | Fix |
|-------|---------|------------|-----|
| All instances on Max | API panes show `Claude Max` | `~/.claude/.credentials.json` has Max auth, overrides API key | Use `CLAUDE_CONFIG_DIR` for API panes |
| API panes stuck in wizard | Interactive setup screens | Fresh config dir has no `.claude.json` | Pre-populate `.claude.json` with onboarding flags |
| Logout affects all instances | After `claude auth logout`, even Max panes go to API | Logout clears `~/.claude/.credentials.json` globally | Never logout; use `CLAUDE_CONFIG_DIR` isolation instead |
| API key visible in pane | Key shown in `export` command output | Env var set via `send-keys` is visible in scrollback | Accepted risk; panes are local-only |
