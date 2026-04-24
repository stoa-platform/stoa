<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
description: AI Factory cost controls, model routing, autonomous levels, Council gate, and token observatory
globs: ".github/workflows/**,.claude/docs/**,.claude/hooks/**"
---

# AI Factory — Cost Model & Autonomous Levels

## Autonomous Levels

| Level | Name | Trigger | Kill-Switch |
|-------|------|---------|-------------|
| L1 | Interactive | `@claude` mention | `DISABLE_L1_INTERACTIVE` |
| L1 | Auto-Review | PR open/sync | `DISABLE_L1_REVIEW` |
| L1 | Issue-to-PR | `claude-implement` label | `DISABLE_L1_IMPLEMENT` |
| L2 | Scheduled | Cron (daily/weekly) | `DISABLE_L2_SCHEDULED` |
| L3 | Linear Pipeline | Ticket → In Progress | `DISABLE_L3_LINEAR` |
| L4 | Self-Improving | Weekly Friday 18:00 | `DISABLE_L4_SELF_IMPROVE` |
| L5 | Multi-Agent | workflow_dispatch | `DISABLE_L5_MULTI_AGENT` |

Kill-switches via GitHub repo variables. No single master switch (intentional).

## Hardening (H24)

Safety: `continue-on-error: true`, fallback comments, diff truncation (500 lines), Council gate, Ask mode for `.claude/docs/` (superseded `.claude/rules/`), timeouts (15-60 min), concurrency groups.

### Council Label State Machine
`[no labels] → council-validated (S1) → ship-fast-path (optional, ≤5pts) → plan-validated (S2)`

## Model Routing

### Local (Claude Code)

| Task | Model | Rationale |
|------|-------|-----------|
| **Implementation** (features, fixes, multi-file) | `claude-opus-4-6` | Fewer turns = lower total cost |
| **Subagent work** (tests, reviews, docs) | `claude-sonnet-4-6` | Isolated scope |
| **Codebase search** | `claude-haiku-4-5-20251001` | Fast, cheap, read-only |
| **Single-file mechanical** | `claude-sonnet-4-6` | Overkill for Opus |

**Escalation**: Sonnet looping > 15 min → switch to Opus. Data: 44% Sonnet sessions > 1h, same tasks < 15 min with Opus.

### CI (GitHub Actions) — via `scripts/ai-ops/model-router.sh`

| Estimate | Model | Max Turns | Est. Cost |
|----------|-------|-----------|-----------|
| ≤3 pts | `claude-haiku-4-5-20251001` | 20 | ~$1 |
| 4-5 pts | `claude-opus-4-6` | 20 | ~$15 |
| 6-8 pts | `claude-opus-4-6` | 30 | ~$18 |
| >8 pts | `claude-opus-4-6` | 40 | ~$25 |

Kill-switch: `CLAUDE_DEFAULT_MODEL` forces single model. Ship fast path: ≤5pt Ship skip S2.

### Effort Level Routing (Opus 4.6)

| Task Mode | Effort | Command | Use When |
|-----------|--------|---------|----------|
| **Ship** (docs, config, deps) | `low` | `/effort low` + `/fast` | Routine, < 5 pts |
| **Show** (refactor, tests, fix) | `medium` | Default | Standard work |
| **Ask** (features, security, MEGAs) | `high` | `/effort high` | Complex, >= 13 pts |

## Council Gate

**Two-Stage**: S1 (ticket pertinence) → S2 (plan validation). Ship ≤5pt skips S2. Threshold: >= 8.0. Model: Sonnet (Council), Haiku (autopilot scan).

Council-free: PR reviews, triage, digests, CI diagnosis, `/sync-plan`.

### Approval Flow
S1: Council → Slack → `/go` → S2. S2: plan → Slack → `/go-plan` → implement. 24h → reminder, 72h → auto-close.

### Velocity Cap
`AUTOPILOT_DAILY_MAX` (default 5). Progressive: Week1=5, Week2=8, Week3=12, Week4+=10.

## Token Budget

| Metric | Threshold | Measured By |
|--------|-----------|-------------|
| Always-loaded rules (no globs) | < 10K bytes | `rules-budget-lint.sh` |
| Any unscoped rule file | < 5K bytes | `rules-budget-lint.sh` |
| MEMORY.md | < 120 lines | `rules-budget-lint.sh` |

**Exception**: `workflow-essentials.md` (~8K, no globs — intentional).

## Token Observatory

### Data Flow
VPS hourly cron (`stoa-infra:deploy/vps/monitoring/cron-token-metrics.sh`) → metrics.log + Pushgateway → Grafana + Daily Slack report

### Thresholds
| Level | Daily Cost | Action |
|-------|-----------|--------|
| Green | < $30 | Normal |
| Yellow | $30-50 | TOKEN-SPEND logged |
| Red | > $50 | COST-ALERT logged, Slack warning |

### API-Equivalent Pricing
| Model | Input/MTok | Output/MTok | Cache Read | Cache Write |
|-------|-----------|-------------|------------|-------------|
| Opus 4.6 | $15 | $75 | $1.50 | $18.75 |
| Sonnet 4.6 | $3 | $15 | $0.30 | $3.75 |
| Haiku 4.5 | $0.80 | $4 | $0.08 | $1 |

## Quality Metrics (AI Regression Tracking)

Script: `scripts/ai-ops/quality-metrics.sh` — weekly cron (Monday 07:00 UTC).

| Metric | Target |
|--------|--------|
| Regression Rate (fix/feat PRs) | < 0.3 |
| Time-to-Regression (avg hours) | > 72h |
| PR Rejection Rate (CI fail on first commit) | < 0.2 |

Green < 0.2, Yellow 0.2-0.4, Red > 0.4 (pause autonomous pipeline).

## Notification Library

`scripts/ai-ops/ai-factory-notify.sh` — pure bash+jq, zero Claude tokens. Key functions: `notify_council`, `notify_implement`, `notify_error`, `notify_plan`, `linear_comment`.

## n8n Integration

Linear → n8n → `repository_dispatch` → GHA. Payload: `ticket_id`, `ticket_title`, `ticket_description`, `priority` + optional `estimate`, `mega_id`, `phase_hint`, `component`.

## GitHub Labels

Automation: `claude-implement`, `council-review`, `ship-fast-path`, `self-improve`, `daily-digest`, `weekly-audit`.
Linear Council: `council:ticket-go/fix/redo` (S1), `council:plan-go/fix/redo` (S2).

## Security

`ANTHROPIC_API_KEY` + `SLACK_WEBHOOK_URL` = GitHub secrets. GHA-hosted runners. No `--dangerously-skip-permissions`. Council = human gate.
