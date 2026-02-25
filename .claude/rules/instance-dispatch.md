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
Session: stoa
+-- Window 0: MONITOR    (htop + watchdog)
+-- Window 1: ORCHESTRE  (user coordination terminal)
+-- Window 2: BACKEND    (STOA_INSTANCE=backend)
+-- Window 3: FRONTEND   (STOA_INSTANCE=frontend)
+-- Window 4: AUTH       (STOA_INSTANCE=auth)
+-- Window 5: MCP        (STOA_INSTANCE=mcp)
+-- Window 6: QA         (STOA_INSTANCE=qa)
```

Each Claude instance at startup:
- `STOA_INSTANCE` env var set -> hook enforces deny rules
- Session startup mechanism loads context automatically (memory.md, plan.md, CLAUDE.md)
- Startup prompt includes: instance role, scope exclusif, max 5 tickets from Linear cycle
- Linear filter: `list_issues(labels: ['instance:<role>'], cycle: current)`

## Billing

| Window | Default Billing | Rationale |
|--------|----------------|-----------|
| BACKEND | Max subscription | Heaviest workload (API + infra) |
| MCP | Max subscription | Complex Rust code |
| FRONTEND | API key | UI work, lighter context |
| AUTH | API key | Narrow scope |
| QA | API key | Read-heavy, write-light |
