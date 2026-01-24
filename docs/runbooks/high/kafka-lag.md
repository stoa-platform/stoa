# Runbook: Kafka/Redpanda - High Consumer Lag

> **Severity**: High
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `KafkaConsumerLagHigh` | `kafka_consumer_group_lag > 10000` | [Kafka Dashboard](https://grafana.gostoa.dev/d/kafka) |
| `KafkaConsumerLagGrowing` | `rate(kafka_consumer_group_lag[5m]) > 100` | [Kafka Dashboard](https://grafana.gostoa.dev/d/kafka) |
| `DeploymentWorkerLagging` | `kafka_consumer_group_lag{group="deployment-worker"} > 1000` | [Deployments](https://grafana.gostoa.dev/d/deployments) |

### Observed Behavior

- API deployments not triggering
- Unprocessed events accumulating
- Delay between UI action and actual effect
- Deployment notifications delayed

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Delayed deployments |
| **APIs** | New versions not deployed on time |
| **SLA** | Deployment delay not met |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check consumer groups and their lag
kubectl exec -n kafka redpanda-0 -- \
  rpk group list

kubectl exec -n kafka redpanda-0 -- \
  rpk group describe deployment-worker

# 2. Check broker status
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster health

# 3. Check consumer pods
kubectl get pods -n stoa-system -l app=control-plane-api
kubectl logs -n stoa-system deploy/control-plane-api --tail=50 | grep -i kafka

# 4. Check topics
kubectl exec -n kafka redpanda-0 -- \
  rpk topic list

# 5. Check throughput
kubectl exec -n kafka redpanda-0 -- \
  rpk topic consume deploy-requests --num 1 --format json
```

### Verification Points

- [ ] Redpanda brokers healthy?
- [ ] Consumer pods running?
- [ ] No deserialization errors?
- [ ] Network OK between consumer and broker?
- [ ] No rebalancing in progress?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Consumer pod down/restart | High | `kubectl get pods` |
| Slow processing (AWX) | High | Logs deployment-worker |
| Message spike | Medium | Topic message rate |
| Consumer rebalancing | Medium | Logs "rebalance" |
| Overloaded broker | Low | Broker metrics |

---

## 3. Resolution

### Immediate Action (mitigation)

```bash
# 1. Check if consumer is stuck
kubectl logs -n stoa-system deploy/control-plane-api --tail=100 | grep -i "kafka\|consumer\|error"

# 2. Restart consumer if stuck
kubectl rollout restart deployment -n stoa-system control-plane-api

# 3. Follow catch-up progress
watch -n 5 "kubectl exec -n kafka redpanda-0 -- rpk group describe deployment-worker"
```

### Resolution by Cause

#### Case 1: Consumer pod down

```bash
# Check pod status
kubectl get pods -n stoa-system -l app=control-plane-api

# If CrashLoopBackOff, check logs
kubectl logs -n stoa-system deploy/control-plane-api --previous

# Restart
kubectl rollout restart deployment -n stoa-system control-plane-api

# Scale to catch up on lag
kubectl scale deployment -n stoa-system control-plane-api --replicas=2
```

#### Case 2: Slow processing (AWX timeouts)

```bash
# Check running AWX jobs
kubectl exec -n stoa-system deploy/control-plane-api -- \
  curl -s localhost:8000/v1/deployments?status=running | jq .

# Check AWX
kubectl get pods -n awx
kubectl logs -n awx deploy/awx-web --tail=50

# If AWX is slow, see AWX runbook
# Temporarily increase consumer timeout
```

#### Case 3: Message spike

```bash
# Check production rate
kubectl exec -n kafka redpanda-0 -- \
  rpk topic describe deploy-requests --print-datadir

# Scale consumers
kubectl scale deployment -n stoa-system control-plane-api --replicas=3

# Increase partitions for parallelism (WARNING: irreversible)
kubectl exec -n kafka redpanda-0 -- \
  rpk topic alter-config deploy-requests --set partition.count=6
```

#### Case 4: Constant consumer rebalancing

```bash
# Check rebalancing logs
kubectl logs -n stoa-system deploy/control-plane-api | grep -i rebalance

# Increase session.timeout.ms and heartbeat.interval.ms
# In Python consumer config:
# session_timeout_ms=30000
# heartbeat_interval_ms=10000

# Restart after config modification
kubectl rollout restart deployment -n stoa-system control-plane-api
```

#### Case 5: Skip stuck messages (last resort)

```bash
# WARNING: Message loss!
# Only if messages are corrupted or impossible to process

# Reset consumer group to latest position
kubectl exec -n kafka redpanda-0 -- \
  rpk group seek deployment-worker --to end

# Or to a specific timestamp
kubectl exec -n kafka redpanda-0 -- \
  rpk group seek deployment-worker --to-timestamp 1703750400000
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] Consumer lag decreasing
- [ ] No errors in logs
- [ ] Deployments resuming
- [ ] Alerts resolved

### Verification Commands

```bash
# Check lag
kubectl exec -n kafka redpanda-0 -- \
  rpk group describe deployment-worker

# Check that messages are being consumed
kubectl exec -n kafka redpanda-0 -- \
  rpk topic consume deploy-results --num 5 --format json

# Check recent deployments
curl -s https://api.gostoa.dev/v1/deployments?limit=5 | jq .
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | If lag continues > 30min | Slack `#platform-team` |
| L3 | Data Team | Kafka/Redpanda issue | @data-team |

---

## 6. Prevention

### Recommended Monitoring

```yaml
groups:
  - name: kafka
    rules:
      - alert: KafkaConsumerLagHigh
        expr: kafka_consumer_group_lag > 10000
        for: 5m
        labels:
          severity: high

      - alert: KafkaConsumerLagGrowing
        expr: rate(kafka_consumer_group_lag[5m]) > 100
        for: 10m
        labels:
          severity: warning

      - alert: KafkaConsumerNotConsuming
        expr: rate(kafka_consumer_group_offset[5m]) == 0
        for: 15m
        labels:
          severity: high
```

### Best Practices

1. **Monitor lag** per consumer group
2. **Configure alerts** before critical accumulation
3. **Auto-scaling** of consumers if possible
4. **Dead letter queue** for unprocessable messages
5. **Retention policy** to prevent infinite accumulation

---

## 7. STOA Kafka Topics

| Topic | Producer | Consumer | Criticality |
|-------|----------|----------|-------------|
| `deploy-requests` | Control-Plane API, Webhooks | Deployment Worker | High |
| `deploy-results` | AWX Callbacks | UI (SSE), Audit | Medium |
| `api-events` | Control-Plane API | Audit, Sync | Medium |
| `tenant-events` | Control-Plane API | Provisioning | Medium |
| `app-events` | IAM Sync | Audit | Low |
| `audit-log` | All services | OpenSearch | Low |

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
