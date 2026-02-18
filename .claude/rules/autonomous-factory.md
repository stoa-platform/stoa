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

| Trigger | Council Mode | Threshold | Approval |
|---------|-------------|-----------|----------|
| Issue labeled `claude-implement` | Full (4 personas, detailed) | >= 8.0 | `/go` on issue |
| Linear ticket → In Progress | Full (4 personas, detailed) | >= 8.0 | `/go` on issue |
| Multi-agent batch dispatch | Quick (4 personas, scores only) | >= 7.0 | `/go-batch` |
| Scheduled CI auto-fix | Skip (Ship mode, no Council) | N/A | Auto |
| Self-improvement proposal | Full (analysis, no code) | >= 8.0 | Label `claude-implement` |
| PR auto-review | Skip (read-only, no changes) | N/A | Auto |
| Daily triage | Skip (read-only, no changes) | N/A | Auto |

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

### Approval Flow

```
Council validates → Slack notification
  ├── User comments `/go` on GitHub issue → Implementation starts
  ├── User comments `/adjust <feedback>` → Council re-runs with feedback
  └── No response in 24h → Reminder sent, then auto-close after 72h
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

### Notification Library (`scripts/ai-ops/ai-factory-notify.sh`)

All Claude workflows use a centralized shell library for Slack notifications, Linear comments, and GHA Job Summaries. Zero extra Claude tokens — pure bash + jq.

**Usage**: `source scripts/ai-ops/ai-factory-notify.sh` at the start of any notification step.

| Function | Purpose | Key Args |
|----------|---------|----------|
| `notify_council` | Council validation report | ticket_id, title, score, verdict, mode, loc, url |
| `notify_implement` | Implementation success/failure | status, ticket_id, pr_num, branch, duration |
| `notify_error` | Vercel-style error with log excerpt | workflow, job, ticket_id, error_excerpt |
| `notify_scan` | Autopilot scan summary | candidates, dispatched, skipped |
| `notify_scheduled` | Daily/weekly task results | emoji, title, message |
| `linear_comment` | Post rich report to Linear ticket | ticket_id, body (markdown) |
| `write_job_summary` | Write to `$GITHUB_STEP_SUMMARY` | job_name, ticket_id, status, pr_num, duration |

**Rules**:
- Notification steps use `continue-on-error: true` (non-blocking)
- `SLACK_WEBHOOK` is optional — graceful no-op if unset
- `LINEAR_API_KEY` is optional — `linear_comment()` is best-effort
- Error excerpts capped at 500 chars via `_extract_error()`
- Old scripts (`slack-notify.sh`, `council-slack-report.sh`, `daily-digest.sh`) are deprecated

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
| Model routing | Haiku/Sonnet/Opus tiers | 3x savings on read-only tasks, better Council quality |
| Max turns per agent | 15 (review), 60 (implementation) | Prevent runaway costs |
| Default model | Sonnet (code gen), Haiku (read-only), Opus (Council) | Right model per task |
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
