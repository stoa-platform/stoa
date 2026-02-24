# Runbook: ArgoCD Policy Drift — GitOps Sync Status

> **Severity**: Medium (single app) / High (multiple apps)
> **Last updated**: 2026-02-24
> **Owner**: Platform Team
> **Linear Issue**: CAB-402
> **Dashboard**: [ArgoCD Drift Monitoring](https://grafana.gostoa.dev/d/argocd-drift)

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Condition | Severity | Dashboard |
|-------|-----------|----------|-----------|
| `ArgoCDAppOutOfSync` | `argocd_app_info{sync_status="OutOfSync"} == 1` for 5min | warning | [Drift Dashboard](https://grafana.gostoa.dev/d/argocd-drift) |
| `ArgoCDMultipleAppsDrifted` | `gitops:apps_out_of_sync:count >= 2` for 5min | critical | [Drift Dashboard](https://grafana.gostoa.dev/d/argocd-drift) |
| `ArgoCDAppDegraded` | `argocd_app_info{health_status="Degraded"} == 1` for 5min | warning | [Drift Dashboard](https://grafana.gostoa.dev/d/argocd-drift) |
| `ArgoCDSyncFailureRateHigh` | sync failure rate >20% for 30min | warning | [Drift Dashboard](https://grafana.gostoa.dev/d/argocd-drift) |
| `ArgoCDMetricsAbsent` | `absent(argocd_app_info)` for 10min | critical | — |

### Observed Behavior

- ArgoCD application showing `OutOfSync` badge in UI
- Slack alert in `#ops-alerts`: "GitOps Drift Detected — `<app-name>`"
- Grafana drift ratio > 0%
- Cluster resources diverged from Git-tracked state

### SLO Impact

**Target**: 0% drift (all applications Synced at all times)
Any persistent OutOfSync state is an SLO violation. Alert fires at 5 minutes.

---

## 2. Quick Diagnosis (< 5 min)

### Step 1: Identify the drifted app

```bash
# List all OutOfSync applications
kubectl get applications -n argocd -o json | \
  jq -r '.items[] | select(.status.sync.status == "OutOfSync") | "\(.metadata.name) — \(.status.sync.status) / \(.status.health.status)"'

# Or via ArgoCD CLI
argocd app list --sync-status OutOfSync --server argocd.gostoa.dev
```

### Step 2: Understand what's drifted

```bash
# Show diff between desired (Git) and live (cluster)
argocd app diff <APP_NAME> --server argocd.gostoa.dev

# Or view in ArgoCD UI:
# https://argocd.gostoa.dev/applications/<APP_NAME>
```

### Step 3: Check sync history

```bash
argocd app history <APP_NAME> --server argocd.gostoa.dev

# Check last sync error
kubectl get application <APP_NAME> -n argocd -o json | \
  jq '.status.operationState.message'
```

---

## 3. Root Cause Classification

| Cause | How to Identify | Resolution |
|-------|----------------|------------|
| Manual cluster edit | `diff` shows resource changed without Git commit | Auto-sync will revert; consider `selfHeal: true` |
| Git push not yet reconciled | Recent commit, sync not triggered | Trigger manual sync |
| Sync failed (manifest error) | `operationState.phase == "Failed"` | Fix manifest in Git, re-sync |
| Resource quota exceeded | Events: `exceeded quota` | Increase quota or reduce resource requests |
| Kyverno policy blocked | Events: `Kyverno` in reason | Fix `securityContext.privileged: false` |
| Network issue (repo unreachable) | `FailedToLoadRepository` | Check repo credentials + network |
| ArgoCD app controller restart | Metrics absent briefly | Verify controller pod running |

---

## 4. Resolution

### Option A: Trigger Manual Sync (safest)

```bash
# Review diff first
argocd app diff <APP_NAME> --server argocd.gostoa.dev

# If diff looks expected (Git is correct), trigger sync
argocd app sync <APP_NAME> --server argocd.gostoa.dev

# Watch sync progress
argocd app wait <APP_NAME> --sync --health --server argocd.gostoa.dev
```

### Option B: Hard Refresh + Sync (bypasses git cache)

```bash
argocd app get --hard-refresh <APP_NAME> --server argocd.gostoa.dev
argocd app sync <APP_NAME> --server argocd.gostoa.dev
```

### Option C: Rollback to last-known-good (if bad Git commit)

```bash
# View history (get the revision ID)
argocd app history <APP_NAME> --server argocd.gostoa.dev

# Rollback to previous revision
argocd app rollback <APP_NAME> <REVISION_ID> --server argocd.gostoa.dev
```

### Option D: Fix manifest in Git (if sync failure due to bad manifest)

1. Identify the failing resource from the sync error message
2. Fix in the GitOps repository
3. Push the fix
4. ArgoCD will auto-detect the new commit (or force-refresh)
5. Re-sync

---

## 5. Verification

```bash
# Verify all apps are Synced and Healthy
kubectl get applications -n argocd -o json | \
  jq -r '.items[] | "\(.metadata.name): sync=\(.status.sync.status) health=\(.status.health.status)"'

# Expected output: all lines show "sync=Synced health=Healthy"

# Verify Grafana alert resolved
# https://grafana.gostoa.dev/d/argocd-drift
# Check: "Apps OutOfSync" stat = 0, "Drift Ratio" = 0%

# Verify Prometheus query returns 0
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 \
  'gitops:apps_out_of_sync:count'
```

---

## 6. Escalation Path

| Level | Who | When |
|-------|-----|------|
| L1 | On-call DevOps | Immediate — manual sync attempt |
| L2 | Platform Team | If sync fails repeatedly or multiple apps drifted |
| L3 | Architecture Team | Systemic drift (Git workflow issue, ArgoCD controller problem) |

**Slack**: `#ops-alerts` (alert auto-posted) → `#platform-team` (escalation)

---

## 7. Prevention

### Enable ArgoCD auto-sync + self-heal

In your Application spec:
```yaml
spec:
  syncPolicy:
    automated:
      prune: true       # Remove resources deleted from Git
      selfHeal: true    # Auto-revert manual cluster changes
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=false
```

### Monitor drift continuously

- **Dashboard**: [ArgoCD Policy Drift](https://grafana.gostoa.dev/d/argocd-drift)
- **Alert threshold**: 5 minutes (SLO) — adjust in `argocd-drift-alerts.yaml` if needed
- **Slack channel**: `#ops-alerts` for all drift events

### GitOps best practices

1. Never edit cluster resources directly — always through Git
2. Use `kubectl diff` before applying manual changes for emergencies
3. Enable `selfHeal: true` for production applications
4. Review ArgoCD sync history weekly: `argocd app history <app> --limit 20`
5. Add `finalizers: resources-finalizer.argocd.argoproj.io` to prevent accidental deletion

---

## 8. References

- [ArgoCD Documentation](https://argo-cd.readthedocs.io)
- [STOA GitOps Architecture](https://docs.gostoa.dev/architecture/gitops)
- [Drift Dashboard](https://grafana.gostoa.dev/d/argocd-drift)
- [ArgoCD UI](https://argocd.gostoa.dev/applications)
- [PrometheusRule: argocd-drift-alerts](../../docker/observability/prometheus/rules/argocd-drift-alerts.yaml)
- [ServiceMonitor: argocd](../../k8s/argocd/argocd-servicemonitor.yaml)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-24 | Platform Team | Initial creation (CAB-402) |
