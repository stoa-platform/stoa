# Runbook: webMethods API Gateway - Down

> **Severity**: Critical
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `GatewayDown` | `up{job="apigateway"} == 0` | [Gateway Dashboard](https://grafana.dev.apim.cab-i.com/d/gateway) |
| `GatewayEndpointDown` | `probe_success{job="blackbox", target=~".*gateway.*"} == 0` | [Blackbox Dashboard](https://grafana.dev.apim.cab-i.com/d/blackbox) |
| `GatewayPodNotReady` | `kube_pod_status_ready{pod=~"apigateway.*"} == 0` | [K8s Dashboard](https://grafana.dev.apim.cab-i.com/d/k8s) |

### Observed Behavior

- All APIs return 502/503/504
- Timeout on `https://gateway.apim.cab-i.com`
- Health check `/rest/apigateway/health` fails
- Developer Portal displays "Gateway unavailable"

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | No API accessible |
| **APIs** | 100% of APIs down |
| **SLA** | Immediate SLA violation - P0 Incident |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check Gateway pods
kubectl get pods -n apim -l app=apigateway

# 2. Check pod logs
kubectl logs -n apim -l app=apigateway --tail=100

# 3. Check deployment
kubectl describe deployment -n apim apigateway

# 4. Check service and endpoints
kubectl get svc -n apim apigateway
kubectl get endpoints -n apim apigateway

# 5. Check Ingress/Gateway API
kubectl get ingress -n apim
kubectl get gateway -n apim
kubectl get httproute -n apim

# 6. Test internal health check
kubectl exec -n apim deploy/apigateway -- \
  curl -s localhost:5555/rest/apigateway/health
```

### Verification Points

- [ ] Gateway pod running?
- [ ] apigateway container ready?
- [ ] elasticsearch sidecar container ready?
- [ ] Service has endpoints?
- [ ] Ingress/HTTPRoute configured?
- [ ] TLS certificate valid?
- [ ] Network policies OK?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Elasticsearch sidecar crash | High | `kubectl logs -n apim deploy/apigateway -c elasticsearch` |
| OOM Kill | High | `kubectl describe pod -n apim -l app=apigateway \| grep -i oom` |
| Expired license | Medium | Gateway logs "license" |
| Full PVC (logs/data) | Medium | `kubectl exec ... -- df -h` |
| Image pull error | Low | `kubectl describe pod` |
| Missing secrets | Low | `kubectl get secrets -n apim` |

---

## 3. Resolution

### Immediate Action (mitigation)

```bash
# 1. If pod is in CrashLoopBackOff, check previous crash logs
kubectl logs -n apim -l app=apigateway --previous

# 2. Force restart deployment
kubectl rollout restart deployment -n apim apigateway

# 3. Follow rollout
kubectl rollout status deployment -n apim apigateway --timeout=5m

# 4. If stuck, increase replicas to have at least one healthy pod
kubectl scale deployment -n apim apigateway --replicas=2
```

### Resolution by Cause

#### Case 1: Elasticsearch sidecar crash

```bash
# Check Elasticsearch logs
kubectl logs -n apim deploy/apigateway -c elasticsearch --tail=50

# If disk full, clean old indices
kubectl exec -n apim deploy/apigateway -c elasticsearch -- \
  curl -X DELETE "localhost:9200/gateway_*_$(date -d '-7 days' +%Y.%m.%d)"

# If heap insufficient, increase resources
kubectl patch deployment -n apim apigateway --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/1/resources/limits/memory", "value": "2Gi"}
]'
```

#### Case 2: OOM Kill

```bash
# Check OOM events
kubectl get events -n apim --field-selector reason=OOMKilled

# Increase memory limits
kubectl patch deployment -n apim apigateway --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "4Gi"},
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/memory", "value": "2Gi"}
]'

# Restart
kubectl rollout restart deployment -n apim apigateway
```

#### Case 3: Expired license

```bash
# Check logs
kubectl logs -n apim deploy/apigateway | grep -i license

# Update license (ConfigMap or Secret)
kubectl create secret generic gateway-license -n apim \
  --from-file=licenseKey.xml=/path/to/new/license.xml \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart to apply
kubectl rollout restart deployment -n apim apigateway
```

#### Case 4: Full PVC

```bash
# Check disk space
kubectl exec -n apim deploy/apigateway -- df -h

# Clean old logs
kubectl exec -n apim deploy/apigateway -- \
  find /opt/softwareag/IntegrationServer/logs -name "*.log" -mtime +7 -delete

# If needed, resize PVC (if StorageClass supports it)
kubectl patch pvc gateway-data -n apim -p '{"spec":{"resources":{"requests":{"storage":"50Gi"}}}}'
```

### Rollback if necessary

```bash
# View deployment history
kubectl rollout history deployment -n apim apigateway

# Rollback to previous version
kubectl rollout undo deployment -n apim apigateway

# Or rollback to a specific revision
kubectl rollout undo deployment -n apim apigateway --to-revision=<N>
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] Gateway pod(s) in Running/Ready state
- [ ] Health check returns 200
- [ ] At least one API responds correctly
- [ ] No errors in logs
- [ ] Prometheus metrics reporting
- [ ] Alerts resolved in Grafana

### Verification Commands

```bash
# Health check
curl -s https://gateway.apim.cab-i.com/rest/apigateway/health | jq .

# Test a public API
curl -s https://gateway.apim.cab-i.com/gateway/ControlPlane/v1/health

# Check metrics
kubectl exec -n apim deploy/apigateway -- \
  curl -s localhost:5555/metrics | head -20

# Check that there are no more alerts
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 \
  'ALERTS{alertname=~"Gateway.*", alertstate="firing"}'
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | If restart fails | Slack `#platform-team` |
| L3 | IBM/Software AG Support | If product issue | Support ticket |

### Emergency Contacts

| Role | Contact |
|------|---------|
| Gateway Expert | @gateway-team |
| Infrastructure | @infra-team |

---

## 6. Prevention

### Recommended Monitoring

```yaml
# Prometheus alerts
groups:
  - name: gateway
    rules:
      - alert: GatewayDown
        expr: up{job="apigateway"} == 0
        for: 1m
        labels:
          severity: critical

      - alert: GatewayHighMemory
        expr: container_memory_usage_bytes{pod=~"apigateway.*"} / container_spec_memory_limit_bytes > 0.85
        for: 5m
        labels:
          severity: warning

      - alert: GatewayHighCPU
        expr: rate(container_cpu_usage_seconds_total{pod=~"apigateway.*"}[5m]) > 0.8
        for: 10m
        labels:
          severity: warning
```

### Best Practices

1. **Configure PodDisruptionBudget** to avoid downtime during maintenance
2. **Enable HPA** for automatic scaling
3. **Configure probes** (liveness, readiness) correctly
4. **Monitor disk space** of PVCs
5. **Renew licenses** before expiration

---

## 7. References

### Documentation

- [webMethods Gateway Administration](https://docs.webmethods.io/)
- [Gateway Troubleshooting Guide](docs/ibm/webmethods-gateway-api.md)

### Grafana Dashboards

- [Gateway Overview](https://grafana.dev.apim.cab-i.com/d/gateway)
- [Gateway Latency](https://grafana.dev.apim.cab-i.com/d/gateway-latency)
- [Gateway Errors](https://grafana.dev.apim.cab-i.com/d/gateway-errors)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
