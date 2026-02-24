---
description: AI Factory token budget and cost controls
globs: ".claude/**"
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

## Model Selection — CI (GitHub Actions)

| Task | Model | Rationale |
|------|-------|-----------|
| **Council S1** (ticket pertinence) | `claude-sonnet-4-6` | Structured eval, 5 turns |
| **Council S2** (plan validation) | `claude-sonnet-4-6` | Structured eval, 10 turns |
| **Autopilot scan** (backlog scoring) | `claude-haiku-4-5-20251001` | Quick scoring, high volume |
| **Implementation ≤5pts** (L1/L3 pipeline) | `claude-sonnet-4-6` | Small tickets, Sonnet sufficient |
| **Implementation >5pts** (L1/L3 pipeline) | `claude-opus-4-6` | Complex tickets hit max_turns with Sonnet (100% failure on 6+ pts) |
| **Auto-review** (PR review) | `claude-sonnet-4-6` | Read-only, structured output |

**Rules**: Max 3-4 subagents active. Prefer haiku for `Explore`. CI implementation stays Sonnet (lighter context = no looping problem).

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
