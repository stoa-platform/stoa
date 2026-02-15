---
globs: "**"
---

# Autonomous AI Factory — Continuous Improvement Loop

## Overview

The STOA AI Factory operates in 5 levels of autonomy. Each level builds on the previous.
Council validation is the gate between "detecting work" and "doing work".

## Levels

| Level | Name | Trigger | Human Input | Status |
|-------|------|---------|-------------|--------|
| L1 | Interactive | `@claude` mention | Per-request | Active |
| L2 | Scheduled | Cron (daily/weekly) | Review digests | Active |
| L3 | Linear Pipeline | Ticket → In Progress | Go/No-Go on Slack | Active |
| L4 | Self-Improving | Weekly retrospective | Approve improvement PRs | Active |
| L5 | Multi-Agent | workflow_dispatch | Batch approval | Active |

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

### Setup Requirements

1. **n8n**: Import `n8n-linear-to-claude.json`
2. **Linear**: Configure webhook pointing to n8n webhook URL
3. **GitHub**: Add PAT as n8n HTTP Header Auth credential
4. **Slack**: Set `SLACK_WEBHOOK` environment variable in n8n

## Cost Control

| Guard | Value | Why |
|-------|-------|-----|
| Max turns per agent | 15 (review), 30 (implementation) | Prevent runaway costs |
| Default model | Sonnet | 10x cheaper than Opus |
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
