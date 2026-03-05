---
description: Autonomous AI Factory levels, kill-switches, Council gate, Slack notifications, n8n integration
globs: ".github/workflows/**"
---

# Autonomous AI Factory — Continuous Improvement Loop

## Levels

| Level | Name | Trigger | Kill-Switch |
|-------|------|---------|-------------|
| L1 | Interactive | `@claude` mention | `DISABLE_L1_INTERACTIVE` |
| L1 | Auto-Review | PR open/sync | `DISABLE_L1_REVIEW` |
| L1 | Issue-to-PR | `claude-implement` label | `DISABLE_L1_IMPLEMENT` |
| L2 | Scheduled | Cron (daily/weekly) | `DISABLE_L2_SCHEDULED` |
| L3 | Linear Pipeline | Ticket → In Progress | `DISABLE_L3_LINEAR` |
| L4 | Self-Improving | Weekly Friday 18:00 | `DISABLE_L4_SELF_IMPROVE` |
| L5 | Multi-Agent | workflow_dispatch | `DISABLE_L5_MULTI_AGENT` |

Kill-switches via GitHub repo variables. Set to `true` to disable. No single master switch (intentional).

## Hardening (H24)

Safety: `continue-on-error: true`, fallback comments, diff truncation (500 lines), Council gate, Ask mode for `.claude/rules/`, timeouts (15-60 min), concurrency groups, Council dedup guards.

### Council Label State Machine

`[no labels] → council-validated (S1) → ship-fast-path (optional, ≤5pts) → plan-validated (S2)`

Guards: skip S1 if `council-validated` exists, skip S2 if `plan-validated` exists, skip issue creation if ticket label exists (L3/L3.5). Cross-workflow dedup via ticket label search.

## Model Routing (via `scripts/ai-ops/model-router.sh`)

| Estimate | Model | Max Turns | Est. Cost |
|----------|-------|-----------|-----------|
| ≤3 pts | `claude-haiku-4-5-20251001` | 20 | ~$1 |
| 4-5 pts | `claude-opus-4-6` | 20 | ~$15 |
| 6-8 pts | `claude-opus-4-6` | 30 | ~$18 |
| >8 pts | `claude-opus-4-6` | 40 | ~$25 |

Kill-switch: `CLAUDE_DEFAULT_MODEL` repo variable forces single model. Ship fast path: ≤5pt Ship tickets skip Stage 2 (~$3 + 5min saved).

### Velocity Cap

`AUTOPILOT_DAILY_MAX` (default 5). Progressive: Week1=5, Week2=8, Week3=12, Week4+=10. Via GitHub repo variables.

## Council Gate

**Two-Stage**: S1 (ticket pertinence, `council:ticket-*` labels) → S2 (plan validation, `council:plan-*` labels). Ship ≤5pt skips S2. Threshold: >= 8.0 (all levels). Model: Sonnet (Council), Haiku (autopilot scan).

Council-free: PR reviews, triage, digests, CI diagnosis, `/sync-plan`.

### Approval Flow

S1: Council → Slack → `/go` → S2 (or auto-implement if Ship ≤5pt). S2: plan → Slack → `/go-plan` → implement. No response 24h → reminder, 72h → auto-close. Batch flows: S1 only → `/go`.

### Council Report Format (Slack)

`:emoji: Council: TICKET-ID — X.XX/10 [Go|Fix|Redo]` + persona table + Ship/Show/Ask mode + LOC + files + approve link.

## Notification Library

`scripts/ai-ops/ai-factory-notify.sh` — pure bash+jq, zero Claude tokens. Sourced by all workflows.

Key functions: `notify_council`, `notify_implement`, `notify_error` (Vercel-style), `notify_reminder`, `notify_scan`, `notify_scheduled`, `notify_pr_hygiene`, `notify_plan`, `linear_comment`, `write_job_summary`, `_react_slack`.

Env vars (all optional, graceful degradation): `SLACK_WEBHOOK`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_THREAD_TS`, `LINEAR_API_KEY`, `N8N_WEBHOOK`, `HMAC_SECRET`.

Threading via `SLACK_THREAD_TS` (n8n payload or captured). Reactions via `_react_slack`. Milestones: `:hammer_and_wrench: started` + `:rocket: PR created` (thread replies, `continue-on-error`).

## Slack `/stoa` Command

Commands: `help|status|scan|implement CAB-XXXX`. 3-tier access: admin (`SLACK_ADMIN_USERS`), allowed (`SLACK_ALLOWED_USERS`), readonly. n8n workflow handles it.

## GitHub Labels

Automation: `claude-implement`, `council-review`, `ship-fast-path`, `self-improve`, `daily-digest`, `weekly-audit`, `ci-failure`, `coverage-drop`.

Linear Council: `council:ticket-go/fix/redo` (S1, green/amber/red), `council:plan-go/fix/redo` (S2, teal/dark-amber/dark-red).

## n8n Integration

Linear → n8n → `repository_dispatch` → GHA. Dispatch payload: `ticket_id`, `ticket_title`, `ticket_description`, `priority` (required) + `estimate`, `mega_id`, `phase_hint`, `component` (optional). n8n enriches `mega_id` from Linear parent.

## Cost Control

Model routing (`model-router.sh`), Ship fast-path (skip S2), velocity cap (`AUTOPILOT_DAILY_MAX`=5), max turns (20/20/30/40), Council threshold 8.0, max 3 parallel agents, timeouts 15-60min, PR Hygiene zero-token, `CLAUDE_DEFAULT_MODEL` kill-switch.

## Security

`ANTHROPIC_API_KEY` + `SLACK_WEBHOOK_URL` = GitHub secrets. GHA-hosted runners. No `--dangerously-skip-permissions`. Council = human gate.
