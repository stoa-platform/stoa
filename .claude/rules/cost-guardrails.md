---
description: AI Factory token budget and cost controls
globs: ".claude/rules/**,.claude/hooks/**"
---

# Cost Guardrails

## Token Budget

| Metric | Threshold | Measured By |
|--------|-----------|-------------|
| Always-loaded rules (no globs) | < 10K bytes | `rules-budget-lint.sh` |
| Any unscoped rule file | < 5K bytes | `rules-budget-lint.sh` |
| MEMORY.md | < 120 lines | `rules-budget-lint.sh` |

**Exception**: `workflow-essentials.md` (behavioral core, ~8K, no globs — intentional).

## Model Selection — Local (Claude Code)

| Task | Model | Rationale |
|------|-------|-----------|
| **Implementation** (features, fixes, debug, deploy, multi-file) | `claude-opus-4-6` | Fewer turns = lower total cost + faster |
| **Subagent work** (tests, reviews, docs) | `claude-sonnet-4-6` | Isolated scope, no looping risk |
| **Codebase search, exploration** | `claude-haiku-4-5-20251001` | Fast, cheap, read-only |
| **Single-file mechanical** (format, config, typo) | `claude-sonnet-4-6` | Overkill for Opus |

**Escalation rule**: Sonnet looping > 15 min → switch to Opus (costs less in total).

**Why Opus for implementation**: With ~40K tokens of system rules, Sonnet saturates its context window after 30+ turns and loops. Opus resolves in 5-15 turns. Data (2026-02-22): 44% of Sonnet sessions > 1h, some > 4h. Same tasks done in < 15 min with Opus.

## Effort Level Routing (Opus 4.6)

Opus 4.6 supports effort levels that trade thoroughness for speed and cost.

| Task Mode | Effort | Command | Use When |
|-----------|--------|---------|----------|
| **Ship** (docs, config, style, deps) | `low` | `/effort low` | Routine, low-risk, < 5 pts |
| **Show** (refactor, tests, bug fix) | `medium` | Default | Standard work, no action needed |
| **Ask** (features, security, MEGAs) | `high` | `/effort high` | Complex, multi-file, >= 13 pts |

**Fast mode**: Toggle `/fast` for Ship tasks — same Opus 4.6 model, faster output. Combine with `low` effort for maximum speed on routine work.

**Subagent effort**: Subagents inherit the parent's effort level. Override with `model` parameter on Agent tool when needed (e.g., `model: haiku` for Explore agents).

## Model Selection — CI (GitHub Actions)

| Task | Model | Rationale |
|------|-------|-----------|
| **Council S1** (ticket pertinence) | `claude-sonnet-4-6` | Structured eval, 5 turns |
| **Council S2** (plan validation) | `claude-sonnet-4-6` | Structured eval, 10 turns |
| **Autopilot scan** (backlog scoring) | `claude-haiku-4-5-20251001` | Quick scoring, high volume |
| **Implementation ≤3pts** (L1/L3 pipeline) | `claude-haiku-4-5-20251001` | Trivial tickets, 80% cheaper, 20 turns |
| **Implementation 4-5pts** (L1/L3 pipeline) | `claude-opus-4-6` | Medium tickets, 20 turns |
| **Implementation 6-8pts** (L1/L3 pipeline) | `claude-opus-4-6` | Complex tickets, 30 turns (100% Sonnet failure on 6+ pts) |
| **Implementation >8pts** (L1/L3 pipeline) | `claude-opus-4-6` | Large tickets, 40 turns |
| **Auto-review** (PR review) | `claude-sonnet-4-6` | Read-only, structured output |

**Rules**: Max 3-4 subagents active. Prefer haiku for `Explore`. CI model routing via `scripts/ai-ops/model-router.sh`.

## Token Observatory (HEGEMON auto-tracked)

### Data Flow
Stop hook → metrics.log + Pushgateway → Grafana + Daily Slack report (VPS cron)

### Metrics Tracked
| Metric | Source | Frequency |
|--------|--------|-----------|
| Daily tokens (per model) | stats-cache.json via stop hook | Every session end |
| Daily cost estimate (API equivalent) | stop-cost-tracker.sh | Every session end |
| Cost alerts (>$50/day) | stop hook → metrics.log | Real-time |
| Daily Slack report | VPS cron → Pushgateway query | Daily 08:00 UTC |
| Grafana dashboard | Pushgateway → Prometheus | Continuous |

### Thresholds
| Level | Daily Cost | Action |
|-------|-----------|--------|
| Green | < $30 | Normal — no notification |
| Yellow | $30-50 | TOKEN-SPEND logged, Grafana visible |
| Red | > $50 | COST-ALERT logged, Slack warning in daily report |

### Metrics Log Events
| Event | Fields | Trigger |
|-------|--------|---------|
| TOKEN-SPEND | date, tokens_total, cost_usd, model, sessions, messages | Every session end |
| COST-ALERT | threshold, actual, date | cost_today > $50 |

### API-Equivalent Pricing (reference)
| Model | Input/MTok | Output/MTok | Cache Read/MTok | Cache Write/MTok |
|-------|-----------|-------------|----------------|-----------------|
| Opus 4.6 | $15 | $75 | $1.50 | $18.75 |
| Sonnet 4.6 | $3 | $15 | $0.30 | $3.75 |
| Haiku 4.5 | $0.80 | $4 | $0.08 | $1 |

## RULES-BUDGET Metric

Format in `metrics.log`:
```
YYYY-MM-DDTHH:MM | RULES-BUDGET | always_loaded_bytes=N files_without_globs=N memory_lines=N
```

Logged by `rules-budget-lint.sh` on every Stop event.

## Quality Metrics (AI Regression Tracking)

Script: `scripts/ai-ops/quality-metrics.sh` — weekly cron (Monday 07:00 UTC).

### Metrics

| Metric | Prometheus Name | What | Target |
|--------|----------------|------|--------|
| Regression Rate | `ai_factory_regression_rate` | fix PRs / feat PRs (AI vs human) | < 0.3 |
| Time-to-Regression | `ai_factory_time_to_regression_hours` | Avg hours feat→fix on same files | > 72h |
| PR Rejection Rate | `ai_factory_pr_rejection_rate` | PRs with CI failure on first commit | < 0.2 |

### Usage

```bash
# Local report (no push)
bash scripts/ai-ops/quality-metrics.sh --days 30

# JSON output for scripting
bash scripts/ai-ops/quality-metrics.sh --days 30 --json

# Push to Pushgateway (cron)
PUSHGATEWAY_URL=https://push.gostoa.dev bash scripts/ai-ops/quality-metrics.sh --push
```

### Thresholds

| Level | Regression Rate | Action |
|-------|----------------|--------|
| Green | < 0.2 | Normal — AI Factory producing stable code |
| Yellow | 0.2 - 0.4 | Review recent feat PRs for test gaps |
| Red | > 0.4 | Pause autonomous pipeline, investigate root cause |
