# Runbook: webMethods API Gateway - High Latency

> **Severity**: High
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `GatewayHighLatencyP95` | `histogram_quantile(0.95, gateway_request_duration) > 2s` | [Gateway Latency](https://grafana.dev.apim.cab-i.com/d/gateway-latency) |
| `GatewayHighLatencyP99` | `histogram_quantile(0.99, gateway_request_duration) > 5s` | [Gateway Latency](https://grafana.dev.apim.cab-i.com/d/gateway-latency) |
| `GatewaySlowBackend` | `backend_response_time > 3s` | [Backend Dashboard](https://grafana.dev.apim.cab-i.com/d/backends) |

### Observed Behavior

- APIs respond slowly (> 2-3 seconds)
- Intermittent timeouts
- Users complain about slowness
- Request queues accumulating

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Degraded experience, frustration |
| **APIs** | Latency SLA not met |
| **SLA** | Potential SLA violation (e.g., P95 < 500ms) |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check latency metrics
kubectl exec -n apim deploy/apigateway -- \
  curl -s localhost:5555/metrics | grep -E "request_duration|latency"

# 2. Check Gateway CPU/Memory load
kubectl top pods -n apim -l app=apigateway

# 3. Check number of requests in progress
kubectl exec -n apim deploy/apigateway -- \
  curl -s localhost:5555/rest/apigateway/analytics/transactionalEvents/count

# 4. Check for slow backends
kubectl logs -n apim deploy/apigateway --tail=100 | grep -i "timeout\|slow\|latency"

# 5. Check Elasticsearch (can cause latency if slow)
kubectl exec -n apim deploy/apigateway -c elasticsearch -- \
  curl -s localhost:9200/_cluster/health | jq .

# 6. Check thread pools
kubectl exec -n apim deploy/apigateway -- \
  curl -s localhost:5555/rest/apigateway/diagnostics/threadpool
```

### Verification Points

- [ ] Gateway CPU < 80%?
- [ ] Gateway Memory OK?
- [ ] Elasticsearch healthy?
- [ ] Backends responding quickly?
- [ ] No excessive GC pauses?
- [ ] Sufficient number of threads?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Slow backend | High | Gateway logs "backend response time" |
| High load (traffic spike) | High | Metrics requests/sec |
| GC pauses (JVM) | Medium | `kubectl logs ... \| grep GC` |
| Slow Elasticsearch | Medium | ES cluster health |
| Saturated thread pool | Medium | Thread pool diagnostics |
| Heavy policies (transformation) | Low | Policy profiling |

---

## 3. Resolution

### Immediate Action (mitigation)

```bash
# 1. Scale horizontally to absorb load
kubectl scale deployment -n apim apigateway --replicas=3

# 2. Check if HPA is active
kubectl get hpa -n apim

# 3. If no HPA, create a temporary one
kubectl autoscale deployment apigateway -n apim \
  --min=2 --max=5 --cpu-percent=70
```

### Resolution by Cause

#### Case 1: Slow backend

```bash
# Identify slow backends via logs
kubectl logs -n apim deploy/apigateway --tail=500 | \
  grep -E "backendResponseTime|backend.*ms" | \
  sort -t'=' -k2 -n -r | head -20

# Check backend health directly
kubectl run curl-test --rm -it --restart=Never \
  --image=curlimages/curl -n apim-system -- \
  curl -w "@-" -o /dev/null -s "https://<BACKEND_URL>/health" <<'EOF'
    time_namelookup:  %{time_namelookup}s\n
    time_connect:     %{time_connect}s\n
    time_appconnect:  %{time_appconnect}s\n
    time_total:       %{time_total}s\n
EOF

# Configure more aggressive timeouts if backend is slow
# In API Gateway config, reduce backend timeout
```

#### Case 2: High load (scaling)

```bash
# Check requests/sec
kubectl exec -n apim deploy/apigateway -- \
  curl -s localhost:5555/metrics | grep "requests_total"

# Increase replicas
kubectl scale deployment -n apim apigateway --replicas=4

# Configure permanent HPA
cat <<EOF | kubectl apply -f -
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: apigateway-hpa
  namespace: apim
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: apigateway
  minReplicas: 2
  maxReplicas: 6
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
EOF
```

#### Case 3: JVM GC Pauses

```bash
# Check GC logs
kubectl logs -n apim deploy/apigateway | grep -i "gc\|pause"

# Increase JVM heap
kubectl patch deployment -n apim apigateway --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/env", "value": [
    {"name": "JAVA_MIN_MEM", "value": "2048m"},
    {"name": "JAVA_MAX_MEM", "value": "4096m"}
  ]}
]'

# Enable G1GC if not already enabled
# -XX:+UseG1GC -XX:MaxGCPauseMillis=200
```

#### Case 4: Slow Elasticsearch

```bash
# Check ES cluster health
kubectl exec -n apim deploy/apigateway -c elasticsearch -- \
  curl -s localhost:9200/_cluster/health?pretty

# Check large indices
kubectl exec -n apim deploy/apigateway -c elasticsearch -- \
  curl -s localhost:9200/_cat/indices?v

# Delete old indices
kubectl exec -n apim deploy/apigateway -c elasticsearch -- \
  curl -X DELETE "localhost:9200/gateway_*_$(date -d '-14 days' +%Y.%m.%d)"

# Reduce log retention if necessary
```

#### Case 5: Saturated thread pool

```bash
# Check thread pools
kubectl exec -n apim deploy/apigateway -- \
  curl -s localhost:5555/rest/apigateway/diagnostics/threadpool | jq .

# Increase thread pool in config
# Configuration in Extended Settings > Thread Pool settings
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] P95 latency < SLA threshold
- [ ] No timeouts
- [ ] CPU/Memory normalized
- [ ] Alerts resolved
- [ ] Backends responding normally

### Verification Commands

```bash
# Latency test
for i in {1..10}; do
  curl -w "Total: %{time_total}s\n" -o /dev/null -s \
    https://gateway.apim.cab-i.com/rest/apigateway/health
done

# Check percentiles
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 \
  'histogram_quantile(0.95, rate(gateway_request_duration_seconds_bucket[5m]))'

# Check alerts
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 \
  'ALERTS{alertname=~".*Latency.*", alertstate="firing"}'
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | If latency persists > 15min | Slack `#platform-team` |
| L3 | Performance Team | Deep analysis required | @performance-team |

---

## 6. Prevention

### Recommended Monitoring

```yaml
groups:
  - name: gateway-latency
    rules:
      - alert: GatewayHighLatencyP95
        expr: histogram_quantile(0.95, rate(gateway_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: high
        annotations:
          summary: "Gateway P95 latency > 2s"

      - alert: GatewayHighLatencyP99
        expr: histogram_quantile(0.99, rate(gateway_request_duration_seconds_bucket[5m])) > 5
        for: 5m
        labels:
          severity: high
```

### Best Practices

1. **Configure HPA** for automatic scaling
2. **Monitor backends** individually
3. **Define reasonable timeouts** per API
4. **Caching** for frequently called APIs
5. **Rate limiting** to prevent overload

---

## 7. References

- [Gateway Performance Tuning](docs/performance-tuning.md)
- [Grafana Gateway Latency](https://grafana.dev.apim.cab-i.com/d/gateway-latency)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
