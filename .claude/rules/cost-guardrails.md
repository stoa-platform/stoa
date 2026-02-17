---
description: AI Factory token budget and cost controls
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
| Codebase search, exploration | haiku | Fast, cheap |
| Subagent work (tests, reviews, docs) | sonnet | Quality/cost balance |
| Architecture, security decisions | opus | Critical reasoning |

**Rules**: Never opus for subagents. Max 3-4 subagents active. Prefer haiku for `Explore`.

## RULES-BUDGET Metric

Format in `metrics.log`:
```
YYYY-MM-DDTHH:MM | RULES-BUDGET | always_loaded_bytes=N files_without_globs=N memory_lines=N
```

Logged by `rules-budget-lint.sh` on every Stop event.
