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

## Model Selection

| Task | Model | Rationale |
|------|-------|-----------|
| Codebase search, exploration | `claude-haiku-4-5-20251001` | Fast, cheap |
| Subagent work (tests, reviews, docs) | `claude-sonnet-4-6` | Quality/cost balance |
| Architecture, security decisions | `claude-opus-4-6` | Critical reasoning |

**Rules**: Never opus for subagents. Max 3-4 subagents active. Prefer haiku for `Explore`.

## RULES-BUDGET Metric

Format in `metrics.log`:
```
YYYY-MM-DDTHH:MM | RULES-BUDGET | always_loaded_bytes=N files_without_globs=N memory_lines=N
```

Logged by `rules-budget-lint.sh` on every Stop event.
