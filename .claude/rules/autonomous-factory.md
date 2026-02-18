---
description: Autonomous AI Factory levels, kill-switches, Council gate, Slack notifications, n8n integration
globs: ".github/workflows/**"
---

# Autonomous AI Factory — Continuous Improvement Loop

## Overview

The STOA AI Factory operates in 5 levels of autonomy. Each level builds on the previous.
Council validation is the gate between "detecting work" and "doing work".

## Levels

| Level | Name | Trigger | Human Input | Status | Kill-Switch |
|-------|------|---------|-------------|--------|-------------|
| L1 | Interactive | `@claude` mention | Per-request | Active | `DISABLE_L1_INTERACTIVE` |
| L1 | Auto-Review | PR open/sync | Async | Active (hardened) | `DISABLE_L1_REVIEW` |
| L1 | Issue-to-PR | `claude-implement` label | `/go` on issue | Active (hardened) | `DISABLE_L1_IMPLEMENT` |
| L2 | Scheduled | Cron (daily/weekly) | Review digests | Active (hardened) | `DISABLE_L2_SCHEDULED` |
| L3 | Linear Pipeline | Ticket → In Progress | Go/No-Go on Slack | Active (hardened) | `DISABLE_L3_LINEAR` |
| L4 | Self-Improving | Weekly Friday 18:00 | Label `claude-implement` | Active (hardened) | `DISABLE_L4_SELF_IMPROVE` |
| L5 | Multi-Agent | workflow_dispatch | Batch approval | Ready (manual only) | `DISABLE_L5_MULTI_AGENT` |

## Kill-Switches

Every level has a kill-switch via GitHub repository variables (`Settings → Secrets and Variables → Actions → Variables`). Set any variable to `true` to disable that level without code changes.

| Variable | Scope | Effect |
|----------|-------|--------|
| `DISABLE_L1_INTERACTIVE` | L1 Interactive | Stops `@claude` mention responses |
| `DISABLE_L1_REVIEW` | L1 Auto-Review | Stops PR auto-review on open/sync |
| `DISABLE_L1_IMPLEMENT` | L1 Issue-to-PR | Stops Council + `/go` implementation flow |
| `DISABLE_L2_SCHEDULED` | L2 Scheduled | Stops all daily/weekly cron tasks |
| `DISABLE_L3_LINEAR` | L3 Linear Pipeline | Stops Linear → Council → PR pipeline |
| `DISABLE_L4_SELF_IMPROVE` | L4 Self-Improving | Stops weekly retrospective analysis |
| `DISABLE_L5_MULTI_AGENT` | L5 Multi-Agent | Stops parallel ticket implementation |

To disable ALL autonomous activity at once, set each variable to `true`. There is no single master switch — this is intentional so levels can be toggled independently.

## Hardening (H24)

All workflows include these safety measures:
- **`continue-on-error: true`** on all Claude Code Action steps — failures are non-blocking
- **Fallback comments** — if Claude fails, a fallback issue/comment is posted with a link to workflow logs
- **Diff truncation** (L1 Review) — PR diffs are truncated to 500 lines to prevent context overflow
- **Council gate** (L1 Issue-to-PR) — `council-validated` label required before `/go` triggers implementation
- **Ask mode enforcement** — rule changes (`.claude/rules/`) are always Ask mode, never auto-merged
- **Timeouts** — every job has an explicit `timeout-minutes` (15-60)
- **Concurrency groups** — prevent parallel runs on the same issue/PR

## Council Gate — Mandatory Validation

**Every autonomous action MUST pass Council validation before execution.**

### When Council Runs

**Two-Stage Gate** (L1 Issue-to-PR, L3 Linear Dispatch):
- **Stage 1** — Ticket Pertinence: "Is this ticket worth implementing?" → `council:ticket-*` labels
- **Stage 2** — Plan Validation: "Is this implementation plan correct?" → `council:plan-*` labels

| Trigger | Stage | Council Mode | Model | Threshold | Approval |
|---------|-------|-------------|-------|-----------|----------|
| Issue labeled `claude-implement` | Stage 1 | Full (4 personas, detailed) | Sonnet | >= 8.0 | `/go` → Stage 2 |
| `/go` on Stage 1 issue | Stage 2 | Full (4 personas, plan-focused) | Sonnet | >= 8.0 | `/go-plan` → implement |
| Linear ticket → In Progress | Stage 1 | Full (4 personas, detailed) | Sonnet | >= 8.0 | `/go` → Stage 2 |
| `/go` on council-review issue | Stage 2 | Full (4 personas, plan-focused) | Sonnet | >= 8.0 | `/go-plan` → implement |
| Multi-agent batch dispatch | Stage 1 only | Quick (4 personas, scores only) | Sonnet | >= 8.0 | `/go-batch` |
| Autopilot backlog scan | Stage 1 only | Quick (4 personas, scores only) | Haiku | >= 8.0 | Slack → `/go` |
| Scheduled CI auto-fix | Skip | — | — | N/A | Auto |
| Self-improvement proposal | Stage 1 only | Full (analysis, no code) | Sonnet | >= 8.0 | Label `claude-implement` |
| PR auto-review | Skip | — | — | N/A | Auto |
| Daily triage | Skip | — | — | N/A | Auto |

### Council-Free Actions (Auto-Approved)

These actions skip Council because they are read-only or trivially reversible:
- PR review comments (no code changes)
- Issue triage and labeling
- Daily/weekly digest generation
- CI failure diagnosis (without auto-fix)
- Plan sync (`/sync-plan`)

### Council Report Format (Slack)

Every Council report posted to Slack MUST include:

```
:emoji: Council: TICKET-ID — X.XX/10 [Go|Fix|Redo]

*Title of the change*

Context: <1-2 sentences on what and why>

| Persona | Score | Verdict |
|---------|-------|---------|
| Chucky | X/10 | Go |
| OSS Killer | X/10 | Go |
| Archi | X/10 | Fix |
| Saul | X/10 | Go |

Ship/Show/Ask: [mode]
Est. LOC: ~XXX
Files: N files in [component]

[Review & Approve] → link to GitHub issue
```

### Approval Flow (Two-Stage)

```
Stage 1: Ticket Pertinence
  Council validates ticket → Slack notification → council:ticket-* label on Linear
    ├── User comments `/go` → Stage 2 starts (plan validation)
    ├── User comments `/adjust <feedback>` → Council re-runs with feedback
    └── No response in 24h → Reminder sent, then auto-close after 72h

Stage 2: Plan Validation (L1 + L3 only)
  Council validates plan → Slack notification → council:plan-* label on Linear
    ├── User comments `/go-plan` → Implementation starts
    ├── User comments `/adjust <feedback>` → Plan re-validated with feedback
    └── No response in 24h → Reminder sent

Batch flows (L3.5 Autopilot, L5 Multi-Agent): Stage 1 only → `/go` starts implementation directly.
```

## Slack Notifications

### Channel Strategy

All AI Factory notifications go to a single Slack channel (configurable via `SLACK_WEBHOOK_URL`).
Message types are distinguished by emoji prefix:

| Emoji | Event | Action Required |
|-------|-------|----------------|
| :white_check_mark: | Council Go (>= 8.0) | Review and `/go` |
| :warning: | Council Fix (6.0-7.9) | Review adjustments, `/go` or `/adjust` |
| :x: | Council Redo (< 6.0) | Revise proposal |
| :rocket: | Implementation started | None (info) |
| :tada: | PR created | Review if Ask mode |
| :merged: | PR merged | None (info) |
| :stethoscope: | CI health check | Review if failures found |
| :shield: | Weekly audit | Review report |
| :brain: | Self-improvement | Review and approve |
| :sunrise: | Daily triage | Review digest |

### Notification Frequency Control

- **Max 10 Slack messages per day** — batch low-priority notifications
- **Council reports**: always immediate (requires human decision)
- **Implementation status**: immediate for Ask mode, batched for Ship/Show
- **Digests**: once daily (07:00 UTC)
- **Audits**: once weekly (Monday 08:00 UTC)

## GitHub Labels for Automation

| Label | Trigger | What Happens |
|-------|---------|-------------|
| `claude-implement` | Added to issue | Council validates → Slack → wait for `/go` → implement |
| `council-review` | Auto-added | Issue has a Council report pending review |
| `self-improve` | Auto-added | Self-improvement proposal |
| `daily-digest` | Auto-added | Daily triage digest |
| `weekly-audit` | Auto-added | Weekly audit report |
| `ci-failure` | Auto-added | CI failure requiring human intervention |
| `coverage-drop` | Auto-added | Test coverage regression |

### Linear Council Labels

| Label | Stage | Score Range | Color | Description |
|-------|-------|-------------|-------|-------------|
| `council:ticket-go` | Stage 1 (Pertinence) | >= 8.0 | green (#0e8a16) | Ticket validated |
| `council:ticket-fix` | Stage 1 (Pertinence) | 6.0 - 7.9 | amber (#e4b400) | Ticket needs adjustments |
| `council:ticket-redo` | Stage 1 (Pertinence) | < 6.0 | red (#d73a49) | Ticket rejected |
| `council:plan-go` | Stage 2 (Plan) | >= 8.0 | teal (#006b75) | Plan validated |
| `council:plan-fix` | Stage 2 (Plan) | 6.0 - 7.9 | dark amber (#b45309) | Plan needs revision |
| `council:plan-redo` | Stage 2 (Plan) | < 6.0 | dark red (#8b0000) | Plan rejected |

## n8n Integration

### Linear → GitHub Pipeline

n8n workflow (`scripts/ai-ops/n8n-linear-to-claude.json`):
1. Linear webhook fires when ticket status → "In Progress"
2. n8n filters for "In Progress" only
3. n8n dispatches `repository_dispatch` to GitHub Actions
4. n8n posts "Pipeline Started" to Slack

### Dispatch Payload Schema

The `repository_dispatch` `client_payload` includes phase-aware fields:

```json
{
  "ticket_id": "CAB-1350",
  "ticket_title": "Traceparent injection",
  "ticket_description": "...",
  "priority": 2,
  "estimate": 5,
  "mega_id": "CAB-1290",
  "phase_hint": 1,
  "component": "gateway"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `ticket_id` | Yes | Linear issue identifier (e.g., `CAB-1350`) |
| `ticket_title` | Yes | Issue title |
| `ticket_description` | Yes | Full issue description + DoD |
| `priority` | Yes | Linear priority (1=Urgent, 4=Low) |
| `estimate` | No | Story points |
| `mega_id` | No | Parent MEGA ticket ID. If present, the dispatched agent checks `.claude/claims/<mega_id>.json` for phase ownership before starting. Prevents L3-dispatched agents from conflicting with local instances. |
| `phase_hint` | No | Suggested phase number within the MEGA. The agent uses this to claim the correct phase instead of scanning all MEGAs. |
| `component` | No | Target component (api, gateway, ui, portal, e2e). Used to select the right CI quality gate. |

**n8n enrichment**: When a ticket has a `parent` in Linear, n8n resolves the parent ID and includes it as `mega_id`. The `phase_hint` is extracted from the ticket's position in the parent's sub-issues list.

### Setup Requirements

1. **n8n**: Import `n8n-linear-to-claude.json`
2. **Linear**: Configure webhook pointing to n8n webhook URL
3. **GitHub**: Add PAT as n8n HTTP Header Auth credential
4. **Slack**: Set `SLACK_WEBHOOK` environment variable in n8n

## Cost Control

| Guard | Value | Why |
|-------|-------|-----|
| Model routing | Haiku/Sonnet tiers | Haiku for read-only, Sonnet for Council + code gen |
| Max turns per agent | 5 (Council), 60 (implementation) | Prevent runaway costs |
| Default model | Sonnet (Council + code gen), Haiku (scan, digest, review) | Right model per task |
| Council threshold | 8.0 (all levels) | Harmonized — no per-level exceptions |
| Max parallel agents | 3 | Cost caps at ~3x single agent |
| Timeout per job | 15-60 min | Hard stop on runaway jobs |
| Skip Council for | Ship-mode, read-only | Avoid unnecessary validation |
| Schedule frequency | Daily/weekly (not hourly) | Control API usage |

## Security

- `ANTHROPIC_API_KEY`: GitHub repo secret, never logged
- `SLACK_WEBHOOK_URL`: GitHub repo secret
- Claude runs on GitHub-hosted runners (code stays on GitHub infra)
- No `--dangerously-skip-permissions` in any workflow
- Council prevents unauthorized changes (human gate)
- All PRs still go through standard CI + security scan
