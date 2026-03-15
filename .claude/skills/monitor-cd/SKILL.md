---
name: monitor-cd
description: Continuous post-merge CD monitoring using /loop. Runs /deploy-check on interval until all checks pass or timeout.
argument-hint: "[interval, e.g. 5m]"
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - WebFetch
---

# Monitor CD — Continuous Deployment Verification

Run continuous CD verification after a merge to main.

## Usage

```
/monitor-cd        → runs /deploy-check every 5 minutes (default)
/monitor-cd 2m     → runs every 2 minutes
```

## Workflow

1. Parse interval from `$ARGUMENTS` (default: `5m`)
2. Use the `/loop` command to schedule recurring `/deploy-check` at the specified interval
3. Each iteration runs the full deploy-check:
   - CI on main (latest workflow run)
   - API health (api.gostoa.dev)
   - Gateway health (mcp.gostoa.dev)
   - Console + Portal (200 check)
   - Pod status (kubectl)
   - ArgoCD sync status
4. Report results as a table after each check
5. Stop automatically when all checks pass (verdict: Go)

## Command

Run this:
```
/loop $ARGUMENTS /deploy-check
```

If `$ARGUMENTS` is empty, use `5m` as default interval.

## When to Use

- After merging a PR to main (especially code changes that trigger Docker build + ArgoCD sync)
- After a hotfix deployment
- When ArgoCD sync seems stuck

## When NOT to Use

- For docs-only changes (no CD pipeline triggered)
- When you can verify manually with a single `/deploy-check`
