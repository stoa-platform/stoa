# Runbook: STOA Operator — Reconciliation Failed

> **Severity**: High
> **Last updated**: 2026-02-15
> **Owner**: Platform Team

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `StoaOperatorReconciliationErrors` | `rate(stoa_reconciliations_total{status="error"}[5m]) > 0` | [STOA Operator Dashboard](https://grafana.gostoa.dev/d/stoa-operator) |
| `StoaOperatorDown` | `stoa_operator_up == 0` | [STOA Operator Dashboard](https://grafana.gostoa.dev/d/stoa-operator) |
| `StoaDriftDetected` | `increase(stoa_drift_detected_total[10m]) > 0` | [Drift Detection Dashboard](https://grafana.gostoa.dev/d/stoa-drift) |

### Observed Behavior

- GatewayInstance (GWI) shows health check failures
- GatewayBinding (GWB) deployments not syncing to gateways
- Drift detected but not auto-remediated
- Operator pod in `CrashLoopBackOff` or stuck in `Running` without processing events

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Gateway configuration stale, new APIs not deployed |
| **APIs** | Drift between desired state (CRDs) and actual gateway config |
| **SLA** | Deployment propagation delayed |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check operator pod status
kubectl get pods -n stoa-system -l app=stoa-operator

# 2. Check operator logs (last 100 lines)
kubectl logs -n stoa-system deploy/stoa-operator --tail=100

# 3. Check operator metrics
kubectl port-forward -n stoa-system deploy/stoa-operator 8000:8000 &
curl -s http://localhost:8000/metrics | grep stoa_

# 4. List GatewayInstance resources
kubectl get gatewayinstances.gostoa.dev -A

# 5. List GatewayBinding resources
kubectl get gatewaybindings.gostoa.dev -A

# 6. Check events
kubectl get events -n stoa-system --sort-by='.lastTimestamp' | grep -i operator | tail -20
```

### Verification Points

- [ ] Operator pod running?
- [ ] `stoa_operator_up` metric = 1.0?
- [ ] Control Plane API reachable from operator pod?
- [ ] CRDs installed (`gatewayinstances.gostoa.dev`, `gatewaybindings.gostoa.dev`)?
- [ ] RBAC: operator ServiceAccount has sufficient permissions?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| CP API auth failure (`X-Operator-Key`) | High | Logs show `401` or `403` on CP API calls |
| CP API unreachable (service down) | High | `curl http://control-plane-api.stoa-system.svc:8000/health` |
| CRD validation error | Medium | `kubectl describe gwi <name>` shows validation failure |
| K8s RBAC insufficient | Medium | Logs show `forbidden` on watch/list/patch |
| Memory/CPU limits hit | Low | `kubectl top pod -n stoa-system -l app=stoa-operator` |
| kopf handler crash | Low | Logs show Python traceback |

---

## 3. Resolution

### Case 1: Control Plane API Auth Failure

The operator authenticates to the CP API using `X-Operator-Key` header.

```bash
# 1. Check the operator's env for the API key
kubectl get deploy stoa-operator -n stoa-system -o jsonpath='{.spec.template.spec.containers[0].env}' | jq .

# 2. Verify the key works
OPERATOR_KEY=$(kubectl get secret stoa-operator-secret -n stoa-system -o jsonpath='{.data.OPERATOR_API_KEY}' | base64 -d)
kubectl exec -n stoa-system deploy/stoa-operator -- \
  curl -s -H "X-Operator-Key: $OPERATOR_KEY" http://control-plane-api.stoa-system.svc:8000/health

# 3. If key is wrong, update the secret
kubectl patch secret stoa-operator-secret -n stoa-system \
  -p="{\"stringData\":{\"OPERATOR_API_KEY\":\"<correct-key>\"}}"

# 4. Restart operator
kubectl rollout restart deployment stoa-operator -n stoa-system
```

### Case 2: Control Plane API Unreachable

```bash
# 1. Check CP API pod status
kubectl get pods -n stoa-system -l app=control-plane-api

# 2. Check service endpoint
kubectl get endpoints control-plane-api -n stoa-system

# 3. Test connectivity from operator pod
kubectl exec -n stoa-system deploy/stoa-operator -- \
  curl -s http://control-plane-api.stoa-system.svc:8000/health

# 4. If CP API is down, resolve CP API issue first (see gateway-down.md)
```

### Case 3: CRD Validation Error

```bash
# 1. Check GWI/GWB resource status
kubectl describe gatewayinstance <name> -n stoa-system

# 2. Verify CRD schema is up to date
kubectl get crd gatewayinstances.gostoa.dev -o jsonpath='{.metadata.resourceVersion}'
kubectl get crd gatewaybindings.gostoa.dev -o jsonpath='{.metadata.resourceVersion}'

# 3. Re-apply CRDs if outdated
kubectl apply -f charts/stoa-platform/crds/gatewayinstances.yaml
kubectl apply -f charts/stoa-platform/crds/gatewaybindings.yaml
```

### Case 4: RBAC Insufficient

```bash
# 1. Check operator ServiceAccount permissions
kubectl auth can-i --as=system:serviceaccount:stoa-system:stoa-operator \
  watch gatewayinstances.gostoa.dev -n stoa-system

# 2. Check ClusterRole bindings
kubectl get clusterrolebinding | grep stoa-operator

# 3. If missing, apply RBAC from Helm chart
kubectl apply -f charts/stoa-platform/templates/operator-rbac.yaml
```

### Case 5: Operator Pod Crash (kopf handler error)

```bash
# 1. Check logs for Python traceback
kubectl logs -n stoa-system deploy/stoa-operator --previous --tail=200

# 2. Common fixes:
#    - Missing env var → check deployment env section
#    - Import error → check image version
#    - Timeout → check network policies

# 3. Restart with fresh state
kubectl rollout restart deployment stoa-operator -n stoa-system
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] Operator pod `Running` and `Ready`
- [ ] `stoa_operator_up` metric = 1.0
- [ ] `stoa_reconciliations_total{status="success"}` incrementing
- [ ] No `stoa_drift_detected_total` increases
- [ ] GWI resources show healthy status
- [ ] GWB deployments synced to target gateways

### Verification Commands

```bash
# Operator health
kubectl get pods -n stoa-system -l app=stoa-operator
curl -s http://localhost:8000/metrics | grep stoa_operator_up

# Reconciliation metrics
curl -s http://localhost:8000/metrics | grep stoa_reconciliations_total

# Drift metrics
curl -s http://localhost:8000/metrics | grep stoa_drift

# CP API request metrics
curl -s http://localhost:8000/metrics | grep stoa_cp_api

# Resources managed count
curl -s http://localhost:8000/metrics | grep stoa_resources_managed
```

---

## 5. Operator Prometheus Metrics Reference

| Metric | Type | Description |
|--------|------|-------------|
| `stoa_operator_up` | gauge | Operator liveness (1.0 = running) |
| `stoa_reconciliations_total` | counter | Total reconciliations by status (success/error) |
| `stoa_reconciliation_duration_seconds` | histogram | Reconciliation loop duration |
| `stoa_cp_api_requests_total` | counter | CP API calls by method and status |
| `stoa_cp_api_duration_seconds` | histogram | CP API call latency |
| `stoa_resources_managed` | gauge | Count of managed GWI + GWB resources |
| `stoa_drift_detected_total` | counter | Drift events detected |
| `stoa_drift_remediated_total` | counter | Drift events auto-remediated |

---

## 6. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | After 30 min without resolution | Slack `#platform-team` |
| L3 | Operator maintainer | kopf framework issues | GitHub Issues |

---

## 7. Prevention

### Best Practices

1. **Monitor `stoa_operator_up`** — alert if it drops to 0
2. **Check reconciliation error rate** — `rate(stoa_reconciliations_total{status="error"}[5m])` should be 0
3. **Review drift metrics** — sustained drift indicates config divergence
4. **Keep CRDs in sync** — apply CRDs before deploying operator updates
5. **Operator image versioning** — use tagged versions (`ghcr.io/stoa-platform/stoa-operator:0.3.0`), not `latest` in production

### Deployment Info

| Cluster | Image | Status |
|---------|-------|--------|
| OVH Prod | `ghcr.io/stoa-platform/stoa-operator:0.3.0` | Running |
| Hetzner Staging | `ghcr.io/stoa-platform/stoa-operator:0.3.0` | Running |

---

## 8. References

### Documentation

- [kopf framework](https://kopf.readthedocs.io/)
- [STOA CRD Reference](https://docs.gostoa.dev/reference/crds/)

### Related Runbooks

- [ArgoCD Out of Sync](../critical/argocd-out-of-sync.md)
- [Gateway Down](../critical/gateway-down.md)
- [Gateway Registration Failed](gateway-registration-failed.md)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-15 | Platform Team | Initial creation (CAB-1030) |
