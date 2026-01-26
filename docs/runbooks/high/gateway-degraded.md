# Runbook: MCP Gateway - Node Degraded (Zombie Detection)

> **Severity**: High
> **Last updated**: 2026-01-26
> **Owner**: Platform Team
> **Linear Issue**: CAB-957

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `GatewayNodeNotReady` | `gateway_readiness_status == 0` for 2m | [Gateway Dashboard](https://grafana.gostoa.dev/d/gateway) |
| `GatewayRequestsRejected` | `increase(stoa_mcp_requests_rejected_total{reason="not_ready"}[5m]) > 10` | [Gateway Dashboard](https://grafana.gostoa.dev/d/gateway) |
| `GatewayZombieNode` | Requests received + low success rate | [Gateway Dashboard](https://grafana.gostoa.dev/d/gateway) |

### Observed Behavior

- Gateway pod shows `ready=false` in `/health/ready` response
- Requests rejected with **503** status code
- Response includes header: `X-STOA-Node-Status: degraded`
- Prometheus metric `stoa_mcp_requests_rejected_total{reason="not_ready"}` increasing

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | MCP clients (Claude, GPT) receive 503 errors |
| **APIs** | Tool invocations fail during degraded period |
| **SLA** | Potential SLA breach if multiple nodes affected |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check pod status and readiness
kubectl get pods -n stoa-system -l app=stoa-mcp-gateway -o wide

# 2. Check readiness probe details
kubectl describe pod -n stoa-system -l app=stoa-mcp-gateway | grep -A 10 "Readiness"

# 3. Check recent logs for readiness failures
kubectl logs -n stoa-system -l app=stoa-mcp-gateway --tail=100 --since=5m | grep -i "ready\|degraded\|failed"

# 4. Check deep readiness endpoint directly
kubectl exec -n stoa-system deploy/stoa-mcp-gateway -- curl -s localhost:8080/health/ready | jq .

# 5. Check events
kubectl get events -n stoa-system --sort-by='.lastTimestamp' | grep -i mcp-gateway | tail -20
```

### Verification Points

- [ ] Pod running? (`kubectl get pods`)
- [ ] Which checks are failing? (Check `/health/ready` response `failed_checks` field)
- [ ] Database reachable? (`kubectl exec ... -- nc -zv postgres-service 5432`)
- [ ] Keycloak reachable? (`kubectl exec ... -- curl -s https://auth.gostoa.dev/health`)
- [ ] Control Plane API reachable? (`kubectl exec ... -- curl -s https://api.gostoa.dev/health`)

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Keycloak rolling update | High | `kubectl get pods -n keycloak-system` |
| Database connection timeout | Medium | Check `failed_checks` contains `database` |
| Network partition | Medium | `kubectl exec ... -- ping -c 3 keycloak-service` |
| Control Plane API down | Low | `kubectl get pods -n stoa-system -l app=control-plane-api` |
| Pod startup (normal) | Normal | Check if pod age < 30s |

---

## 3. Resolution

### Immediate Action (mitigation)

> **Objective**: Traffic is already isolated by K8s (readiness=false removes from Service)

```bash
# 1. Verify pod is removed from Service endpoints
kubectl get endpoints stoa-mcp-gateway -n stoa-system -o yaml

# 2. Check if other pods are healthy (traffic should route to them)
kubectl get pods -n stoa-system -l app=stoa-mcp-gateway -o wide

# 3. If ALL pods are degraded, check shared dependencies
kubectl get pods -n keycloak-system
kubectl get pods -n stoa-system -l app=control-plane-api
kubectl get pods -n stoa-system -l app=postgres
```

### Corrective Action (fix root cause)

> **Objective**: Restore the failing dependency

**If Keycloak is down:**
```bash
kubectl rollout restart deployment/keycloak -n keycloak-system
kubectl rollout status deployment/keycloak -n keycloak-system
```

**If Database is unreachable:**
```bash
kubectl get pods -n stoa-system -l app=postgres
kubectl logs -n stoa-system -l app=postgres --tail=50
# If stuck, restart
kubectl rollout restart statefulset/postgres -n stoa-system
```

**If Control Plane API is down:**
```bash
kubectl rollout restart deployment/control-plane-api -n stoa-system
kubectl rollout status deployment/control-plane-api -n stoa-system
```

**If pod is stuck:**
```bash
# Force restart the degraded pod
kubectl delete pod <pod-name> -n stoa-system
# New pod will start with fresh connections
```

### Rollback if necessary

```bash
# If recent deployment caused the issue
kubectl rollout undo deployment/stoa-mcp-gateway -n stoa-system
kubectl rollout status deployment/stoa-mcp-gateway -n stoa-system
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] All pods show `Ready: True` in `kubectl get pods`
- [ ] `/health/ready` returns `{"status": "healthy"}` with 200
- [ ] Prometheus metric `stoa_mcp_requests_rejected_total` stopped increasing
- [ ] Alert resolved in Grafana
- [ ] Test MCP tool invocation works

### Verification Commands

```bash
# Service verification
kubectl exec -n stoa-system deploy/stoa-mcp-gateway -- curl -s localhost:8080/health/ready | jq .

# Metrics verification
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 'stoa_mcp_requests_rejected_total'

# End-to-end test
curl -s https://mcp.gostoa.dev/healthz | jq .
```

---

## 5. Known False Positives

> **These conditions cause temporary not_ready state — this is NORMAL, no escalation needed**

| Condition | Duration | Action |
|-----------|----------|--------|
| Keycloak rolling update | 30-60s | Wait for Keycloak to stabilize |
| Database maintenance window | During window | Expected, documented in change calendar |
| Pod startup during scale-up | 10-30s | Normal, `initialDelaySeconds` handles this |
| Network partition recovery | 5-15s | Transient, auto-recovers |
| Control Plane API restart | 30-60s | Wait for API to stabilize |

**Decision tree:**
1. Is this a known maintenance window? → **No action needed**
2. Is pod age < 60 seconds? → **Wait for startup to complete**
3. Is only 1 of N pods affected? → **Traffic routes to healthy pods, investigate calmly**
4. Are ALL pods affected? → **Investigate shared dependency (Keycloak, DB, API)**

---

## 6. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | After 15 min without resolution | Slack `#platform-team` |
| L3 | Infrastructure Team | If Keycloak/DB/Network issue | Slack `#infra-team` |

### Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Platform Lead | - | @platform-lead |
| Security | - | @security-team |
| Infrastructure | - | @infra-team |

---

## 7. Post-mortem

### To document after resolution

- [ ] Incident timeline
- [ ] Root cause identified (which component failed?)
- [ ] Was this a known false positive?
- [ ] Preventive actions defined
- [ ] Runbook updated if necessary

### Post-mortem Template

```markdown
## Incident: MCP Gateway Degraded
**Date**: YYYY-MM-DD HH:MM
**Duration**: X minutes
**Severity**: High

### Timeline
- HH:MM - Alert fired: GatewayNodeNotReady
- HH:MM - Investigation started
- HH:MM - Root cause identified: [component]
- HH:MM - Resolution applied
- HH:MM - Service restored

### Root Cause
[Which dependency failed? Why?]

### Preventive Actions
- [ ] Action 1
- [ ] Action 2
```

---

## 8. References

### Documentation

- [ADR-025: Anti-Zombie Node Pattern](https://docs.gostoa.dev/architecture/adr/adr-025-gateway-resilience-zombie)
- [MCP Gateway Architecture](../concepts/mcp-gateway.md)
- [STOA Platform Architecture](../ARCHITECTURE-PRESENTATION.md)

### Grafana Dashboards

- [MCP Gateway Dashboard](https://grafana.gostoa.dev/d/gateway)
- [Keycloak Dashboard](https://grafana.gostoa.dev/d/keycloak)
- [Infrastructure Dashboard](https://grafana.gostoa.dev/d/infra)

### Related Runbooks

- [Keycloak Down](./keycloak-down.md)
- [Database Connection Issues](./database-connection.md)
- [Control Plane API Errors](./control-plane-api-errors.md)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-01-26 | CAB-957 | Initial creation |
