# Runbook: Prometheus Alerting — Quick Response Guide

> **Severity**: Varies per alert
> **Last updated**: 2026-04-04
> **Owner**: Platform Team

---

## STOA Gateway

### stoa-gateway-errors

**Alert**: `StoaGatewayHighErrorRate` — tool error rate > 5% for 5 min.

```bash
# Check error logs
kubectl logs -n stoa-system -l app=stoa-gateway --tail=200 --since=10m | grep -i error

# Check error rate breakdown
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 \
  'sum by (status) (rate(stoa_mcp_tools_calls_total[5m]))'
```

**Common causes**: upstream backend down, invalid tool config, auth token expired.
**Mitigation**: check backend health, restart gateway pod if stuck.

### stoa-gateway-latency

**Alert**: `StoaGatewayHighLatency` — P99 > 2s for 5 min.

```bash
# Check latency percentiles
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 \
  'histogram_quantile(0.99, sum(rate(stoa_mcp_tool_duration_seconds_bucket[5m])) by (le))'

# Check resource usage
kubectl top pods -n stoa-system -l app=stoa-gateway
```

**Common causes**: backend slow, resource exhaustion, network congestion.
**Mitigation**: check backend latency, scale if CPU/mem > 80%.

### stoa-gateway-down

**Alert**: `StoaGatewayDown` — `up{job="stoa-gateway"} == 0` for 1 min.

```bash
# Check pod status
kubectl get pods -n stoa-system -l app=stoa-gateway -o wide
kubectl describe pod -n stoa-system -l app=stoa-gateway | tail -30

# Check recent events
kubectl get events -n stoa-system --sort-by='.lastTimestamp' | grep gateway | tail -10

# Restart if CrashLoopBackOff
kubectl rollout restart deployment/stoa-gateway -n stoa-system
```

**Common causes**: OOM kill, config error, missing secrets, Kyverno block.

### stoa-gateway-oidc

**Alert**: `StoaGatewayOidcFailure` — errors but zero success for 5 min.

```bash
# Check Keycloak reachability from gateway
kubectl exec -n stoa-system deploy/stoa-gateway -- \
  curl -s -o /dev/null -w "%{http_code}" ${STOA_AUTH_URL}/realms/stoa/.well-known/openid-configuration

# Check gateway OIDC config
kubectl describe deployment/stoa-gateway -n stoa-system | grep -E 'KEYCLOAK|OIDC|AUTH'
```

**Common causes**: Keycloak down, realm misconfigured, OIDC secret rotated without gateway restart.
**Mitigation**: verify Keycloak health, restart gateway if secret was rotated.

---

## Control Plane API

### control-plane-api-errors

**Alert**: `ControlPlaneAPIHighErrorRate` — 5xx rate > 5% for 5 min.

```bash
kubectl logs -n stoa-system -l app=control-plane-api --tail=200 --since=10m | grep -E "500|502|503"
kubectl top pods -n stoa-system -l app=control-plane-api
```

**Common causes**: database connection pool exhausted, Keycloak unreachable, unhandled exception.

### control-plane-api-latency

**Alert**: `ControlPlaneAPIHighLatency` — P95 > 2s for 5 min.

```bash
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 \
  'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="control-plane-api"}[5m])) by (le))'
```

**Common causes**: slow DB queries, N+1 queries, external service timeout.

### control-plane-api-down

**Alert**: `ControlPlaneAPIDown` — `up == 0` for 1 min.

```bash
kubectl get pods -n stoa-system -l app=control-plane-api -o wide
kubectl logs -n stoa-system -l app=control-plane-api --previous --tail=50
kubectl rollout restart deployment/control-plane-api -n stoa-system
```

---

## Database

### database-down

**Alert**: `DatabaseDown` — `pg_up == 0` for 1 min.

```bash
# Check PostgreSQL pod
kubectl get pods -n stoa-system -l app=postgresql -o wide

# Check PVC space
kubectl exec -n stoa-system postgresql-0 -- df -h /var/lib/postgresql/data

# Check connections
kubectl exec -n stoa-system postgresql-0 -- \
  psql -U stoa -c "SELECT count(*) FROM pg_stat_activity;"
```

**Common causes**: disk full, OOM, too many connections, PVC issue.

---

## Kubernetes

### pod-not-ready

**Alert**: `PodNotReady` — pod not ready for 5 min.

```bash
kubectl get pods -n stoa-system -o wide | grep -v Running
kubectl describe pod <pod-name> -n stoa-system | tail -30
kubectl get events -n stoa-system --sort-by='.lastTimestamp' | tail -20
```

**Common causes**: failing readiness probe, missing configmap/secret, image pull error, Kyverno block.

### pod-crash-loop

**Alert**: `PodCrashLooping` — > 3 restarts in 15 min.

```bash
# Check crash reason
kubectl logs -n stoa-system <pod-name> --previous --tail=100

# Check exit code
kubectl get pod <pod-name> -n stoa-system -o jsonpath='{.status.containerStatuses[0].lastState.terminated}'
```

**Common causes**: missing env var, bad config, DB migration failure, OOM.

---

## Disk

### disk-space-low

**Alert**: `DiskSpaceHigh` — < 20% free.

```bash
# Check node disk
kubectl get nodes -o wide
kubectl exec -n monitoring node-exporter-<hash> -- df -h

# Find large files
kubectl exec -n stoa-system <pod> -- du -sh /var/log/* | sort -rh | head -5
```

**Mitigation**: clean old logs, PVC resize, evict unused images.

### disk-space-critical

**Alert**: `DiskSpaceCritical` — < 10% free. **Immediate action required.**

Same commands as above. Additionally:
```bash
# Emergency: clean container logs
kubectl get nodes -o name | xargs -I{} kubectl debug {} -- \
  find /var/log/containers -name "*.log" -mtime +7 -delete
```

---

## Keycloak

### keycloak-down

**Alert**: `KeycloakDown` — `up == 0` for 1 min.

```bash
kubectl get pods -n stoa-system -l app=keycloak -o wide
kubectl logs -n stoa-system -l app=keycloak --tail=100
curl -s -o /dev/null -w "%{http_code}" ${STOA_AUTH_URL}/health/ready
```

**Common causes**: JVM heap exhausted, DB connection lost, bad realm import.
**Impact**: all auth flows broken (Console, Portal, Gateway OIDC).

---

## Redpanda / Kafka

### redpanda-down

**Alert**: `RedpandaDown` — `up == 0` for 1 min.

```bash
kubectl get pods -n stoa-system -l app=redpanda -o wide
kubectl logs -n stoa-system -l app=redpanda --tail=100

# Check topics
kubectl exec -n stoa-system redpanda-0 -- rpk topic list
```

**Common causes**: disk full, node affinity broken, PVC issue.
**Impact**: event streaming stopped, async operations (catalog sync, metering) delayed.

---

## SLO / Error Budget

### error-budget-low

**Alert**: `ErrorBudgetLow` — < 20% remaining.

Review recent incidents and error trends. Consider freezing non-critical deploys.

```bash
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 'slo:error_budget:remaining_ratio'
```

### error-budget-exhausted

**Alert**: `ErrorBudgetExhausted` — < 5% remaining. **Freeze non-critical deployments.**

Escalate to Platform Lead. Only critical fixes allowed until budget recovers.

---

## Escalation

| Level | Who | When |
|-------|-----|------|
| L1 | On-call DevOps | Immediate |
| L2 | Platform Team | After 15 min without resolution |
| L3 | Vendor Support | If blocked or major incident |
