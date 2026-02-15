# Runbook: ArgoCD — Application Out of Sync

> **Severity**: Critical
> **Last updated**: 2026-02-15
> **Owner**: Platform Team

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `ArgoCDAppOutOfSync` | `argocd_app_info{sync_status!="Synced"}` for 10m | [ArgoCD Dashboard](https://grafana.gostoa.dev/d/argocd) |
| `ArgoCDAppDegraded` | `argocd_app_info{health_status="Degraded"}` for 5m | [ArgoCD Dashboard](https://grafana.gostoa.dev/d/argocd) |

### Observed Behavior

- ArgoCD UI shows application as `OutOfSync` or `Degraded`
- Deployment not updated after merge to main
- New pods not rolling out
- `kubectl get applications -n argocd` shows sync errors

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Running stale version of the service |
| **APIs** | New features/fixes not deployed |
| **SLA** | Deployment latency SLA violated |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. List all ArgoCD applications with status
kubectl get applications -n argocd -o custom-columns=\
'NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision'

# 2. Get detailed sync status for a specific app
kubectl get application <app-name> -n argocd -o yaml | grep -A 20 'status:'

# 3. Check ArgoCD controller logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller --tail=50

# 4. Check ArgoCD repo server (git access)
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-repo-server --tail=50

# 5. Check events
kubectl get events -n argocd --sort-by='.lastTimestamp' | tail -20
```

### Verification Points

- [ ] ArgoCD controller pod running?
- [ ] ArgoCD repo-server can reach GitHub?
- [ ] Git revision matches expected HEAD?
- [ ] Target namespace exists?
- [ ] RBAC allows ArgoCD to manage resources?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Immutable field changed (selector, etc.) | High | Sync error mentions `field is immutable` |
| Kyverno policy blocking pod creation | High | Events show `policy ... blocked` |
| Git repo access token expired | Medium | Repo-server logs show `authentication failed` |
| Ingress hostname conflict | Medium | Two apps claim same host |
| Resource quota exceeded | Low | Events show `exceeded quota` |
| CRD missing or outdated | Low | Sync error mentions `no matches for kind` |

---

## 3. Resolution

### Case 1: Immutable Field Changed (`spec.selector` is immutable)

This happens when Helm chart or manifest changes a label selector, which K8s does not allow on existing deployments.

```bash
# 1. Identify the blocking resource
kubectl get application <app-name> -n argocd -o jsonpath='{.status.conditions[*].message}'

# 2. Delete the blocking deployment (ArgoCD will recreate it)
kubectl delete deployment <deployment-name> -n stoa-system

# 3. Trigger manual sync
kubectl patch application <app-name> -n argocd --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'

# 4. Verify sync completes
kubectl get application <app-name> -n argocd -w
```

### Case 2: Kyverno Policy Blocking Pod Creation

The cluster has a `restrict-privileged` Kyverno policy in **Enforce** mode. Every container MUST have `securityContext.privileged: false` explicitly set.

```bash
# 1. Check Kyverno policy reports
kubectl get policyreport -n stoa-system

# 2. Check events for policy blocks
kubectl get events -n stoa-system | grep -i kyverno

# 3. Fix: add explicit securityContext to deployment manifest
# securityContext:
#   privileged: false
#   runAsNonRoot: true
#   allowPrivilegeEscalation: false

# 4. After fixing manifest, push to main and wait for ArgoCD sync
```

### Case 3: Git Repo Access Token Expired

ArgoCD uses a GitHub token (`x-access-token`) to pull from the `stoa-platform/stoa` repo.

```bash
# 1. Check repo server connectivity
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-repo-server --tail=20 | grep -i "auth\|denied\|expired"

# 2. Check the repo secret
kubectl get secret -n argocd -l argocd.argoproj.io/secret-type=repository -o yaml

# 3. Update the token (replace with fresh GitHub PAT)
kubectl edit secret <repo-secret-name> -n argocd
# Update 'password' field with base64-encoded new token

# 4. Restart repo server to pick up new creds
kubectl rollout restart deployment argocd-repo-server -n argocd
```

**Gotcha**: Helm-created repo secret can conflict with a manually created one. If both exist, delete the Helm-created secret and keep the manual one with `x-access-token`.

### Case 4: Ingress Hostname Conflict

Two ArgoCD applications claim the same ingress hostname.

```bash
# 1. List all ingresses
kubectl get ingress -n stoa-system

# 2. Identify the conflict
kubectl get ingress -A -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,HOSTS:.spec.rules[*].host'

# 3. Disable ingress on the incorrect application
# Edit the ArgoCD Application to set ingress.enabled=false in Helm values override

# 4. Sync
kubectl patch application <wrong-app> -n argocd --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'
```

### Case 5: Force Sync (last resort)

If the diff is expected and you want to force ArgoCD to accept the live state:

```bash
# Force sync with replace strategy (destructive — replaces resources)
kubectl patch application <app-name> -n argocd --type merge -p '{
  "operation": {
    "sync": {
      "revision": "HEAD",
      "syncStrategy": {
        "apply": {
          "force": true
        }
      }
    }
  }
}'
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] Application shows `Synced` + `Healthy`
- [ ] Pod is running with correct image
- [ ] Service endpoint responds
- [ ] No sync errors in ArgoCD UI
- [ ] No Kyverno policy violations

### Verification Commands

```bash
# ArgoCD app status
kubectl get application <app-name> -n argocd -o custom-columns=\
'SYNC:.status.sync.status,HEALTH:.status.health.status'

# Pod running with correct image
kubectl get pods -n stoa-system -l app=<component> -o jsonpath='{.items[0].spec.containers[0].image}'

# Service health
curl -s https://<service>.gostoa.dev/health | jq .

# ArgoCD sync history
kubectl get application <app-name> -n argocd -o jsonpath='{.status.history[-1:]}'
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | After 15 min without resolution | Slack `#platform-team` |
| L3 | ArgoCD community | Raft/controller issues | GitHub Issues |

---

## 6. Prevention

### Recommended Monitoring

```yaml
groups:
  - name: argocd
    rules:
      - alert: ArgoCDAppOutOfSync
        expr: argocd_app_info{sync_status!="Synced"} == 1
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "ArgoCD app {{ $labels.name }} is out of sync"

      - alert: ArgoCDAppDegraded
        expr: argocd_app_info{health_status="Degraded"} == 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "ArgoCD app {{ $labels.name }} is degraded"
```

### Best Practices

1. **Always use auto-sync + self-heal** for production apps (prevents manual drift)
2. **Never change `spec.selector`** in deployment manifests — K8s treats these as immutable
3. **Explicit `privileged: false`** on all containers (Kyverno Enforce policy)
4. **Test Helm chart changes** with `helm template` before pushing
5. **Monitor repo-server logs** for auth failures (token expiry is silent)

### Known Issues (from production experience)

| Issue | Cause | Workaround |
|-------|-------|------------|
| `OutOfSync` + `spec.selector: immutable` | Helm chart label selector changed | Delete deployment, let ArgoCD recreate |
| `Degraded` + ingress conflict | Two apps claim same host | Disable ingress on wrong app |
| `OutOfSync` + Kyverno blocked | Missing `privileged: false` | Add to values.yaml securityContext |
| `Unknown` + Healthy | App source unreachable or auto-sync off | Check repo access, manual sync |
| Helm-created repo secret conflict | Both Helm and manual secrets exist | Delete Helm one, keep manual with `x-access-token` |
| Hetzner CoreDNS caching | `forward /etc/resolv.conf` uses Hetzner DNS | Change to `forward . 1.1.1.1 8.8.8.8` |

---

## 7. References

### Documentation

- [ArgoCD Troubleshooting](https://argo-cd.readthedocs.io/en/stable/operator-manual/troubleshooting/)
- [ArgoCD Sync Options](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/)

### STOA ArgoCD Setup

| Cluster | ArgoCD URL | Auth |
|---------|-----------|------|
| OVH Prod | `https://argocd.gostoa.dev` | Keycloak SSO |
| Hetzner Staging | `https://staging-argocd.gostoa.dev` | Keycloak SSO |

### Managed Applications

| Application | Component | Deploy Method |
|-------------|-----------|---------------|
| `stoa-gateway` | Rust gateway | `kubectl rollout restart` |
| `control-plane-api` | Python API | `kubectl set image` |
| `control-plane-ui` | React Console | `kubectl apply` + `set image` |
| `stoa-portal` | React Portal | `kubectl apply` + `set image` |
| `mcp-gateway` | Python MCP GW | `kubectl set image` |

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-15 | Platform Team | Initial creation (CAB-1030) |
