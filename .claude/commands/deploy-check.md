Post-merge CD verification. Run after merging a PR to main.

Check each step and report Go/Fix:

1. **CI on main**: `gh run list --branch main --limit 5 --json status,conclusion,name,headSha` — latest must be `success`
2. **API health**: `curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://api.gostoa.dev/health` — must be 200
3. **Gateway health**: `curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://mcp.gostoa.dev/health` — must be 200
4. **Console**: `curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://console.gostoa.dev` — must be 200
5. **Portal**: `curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://portal.gostoa.dev` — must be 200
6. **Pods**: `kubectl get pods -n stoa-system -o wide` — all Running, no CrashLoopBackOff
7. **ArgoCD**: `kubectl get applications -n argocd -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'` — all Synced+Healthy
8. **Images**: `kubectl get deployments -n stoa-system -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image'` — verify latest tags

Output a table:

| # | Check | Status | Detail |
|---|-------|--------|--------|

Verdict: **Go** (all pass) or **Fix** (any fail + corrective actions).
