# Runbook: Kafka Multi-tenant Quotas — Noisy Neighbor Prevention

> **Severity**: Medium
> **Last updated**: 2026-02-20
> **Owner**: Platform Team
> **Linear Issue**: CAB-499

---

## 1. Overview

Kafka tenant quotas prevent "noisy neighbor" issues in multi-tenant environments by limiting the rate at which individual tenants can produce and consume messages. Without quotas, a single misbehaving or high-volume tenant can monopolize broker resources, degrading performance for all other tenants.

### Quota Tiers

STOA implements two quota tiers:

| Tier | Producer Rate | Consumer Rate | CPU Request % | Client-ID Prefix |
|------|--------------|--------------|---------------|------------------|
| **Standard** | 10 MB/s | 20 MB/s | 25% | `tenant-{tenant_id}` |
| **Premium** | 50 MB/s | 100 MB/s | 50% | `tenant-premium-{tenant_id}` |

---

## 2. Quota Configuration

### Automatic Configuration

Tenant quotas are automatically applied during tenant provisioning via the Control Plane API:

```python
from src.services.kafka_service import kafka_service

# Configure standard tier quota
await kafka_service.configure_tenant_quota("acme", tier="standard")

# Configure premium tier quota
await kafka_service.configure_tenant_quota("acme", tier="premium")
```

### Manual Configuration

To manually configure quotas for a specific tenant:

```bash
# Via kubectl and rpk (Redpanda CLI)
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas set \
  --client-id tenant-acme \
  --producer-byte-rate 10485760 \
  --consumer-byte-rate 20971520
```

### Verify Quota Configuration

```bash
# Check all quotas
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe

# Check specific client-id pattern
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe --client-id tenant-acme
```

---

## 3. Monitoring Quota Violations

### Prometheus Alerts

```yaml
groups:
  - name: kafka-quotas
    rules:
      - alert: KafkaQuotaViolation
        expr: kafka_quota_exceeded_count > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Tenant {{ $labels.client_id }} exceeding Kafka quotas"
          description: "Tenant has been throttled {{ $value }} times in the last 5 minutes"
```

### Check Quota Violations

```bash
# View throttled clients
kubectl exec -n kafka redpanda-0 -- \
  rpk topic consume stoa.metering.events \
  --format json \
  --num 100 | jq 'select(.payload.throttled == true)'

# Check broker metrics
kubectl exec -n kafka redpanda-0 -- \
  curl -s http://localhost:9644/metrics | grep quota
```

---

## 4. Troubleshooting

### Symptom: Tenant reports slow event processing

**Diagnosis**:
```bash
# Check if tenant is being throttled
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe --client-id tenant-acme

# View recent throttle events
kubectl logs -n stoa-system deploy/control-plane-api --tail=100 | grep -i "quota\|throttle"
```

**Resolution**:
1. **If quota is legitimate**: Tenant is generating traffic beyond their tier limits
   - Option A: Upgrade tenant to premium tier
   - Option B: Optimize tenant's event generation pattern
   - Option C: Increase quota for this specific tenant (requires approval)

2. **If quota is too restrictive**: Adjust tier limits
   ```python
   # Update QuotaTier.STANDARD or QuotaTier.PREMIUM in kafka_service.py
   # Redeploy control-plane-api
   kubectl rollout restart deployment/control-plane-api -n stoa-system
   ```

### Symptom: Quota not being enforced

**Diagnosis**:
```bash
# Verify admin client is connected
kubectl logs -n stoa-system deploy/control-plane-api | grep "Kafka admin client"

# Check if quota entity exists
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe
```

**Resolution**:
```bash
# Re-apply quota configuration
kubectl exec -n stoa-system deploy/control-plane-api -- \
  python3 -c "
import asyncio
from src.services.kafka_service import kafka_service
asyncio.run(kafka_service.connect())
kafka_service.configure_tenant_quota('acme', 'standard')
"

# Verify applied
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe --client-id tenant-acme
```

---

## 5. Best Practices

### Fair Usage Policy

1. **Default all new tenants to standard tier**
2. **Premium tier requires approval** (sales/platform team)
3. **Monitor quota violations** and reach out proactively
4. **Document quota tiers** in customer-facing SLA documentation

### Client-ID Naming Convention

Producers and consumers MUST use the correct client-id prefix:

```python
# Python (kafka-python)
producer = KafkaProducer(
    bootstrap_servers=["redpanda:9092"],
    client_id=f"tenant-{tenant_id}-producer-{uuid.uuid4().hex[:8]}",
)

# Python (kafka-python) — premium tier
producer = KafkaProducer(
    bootstrap_servers=["redpanda:9092"],
    client_id=f"tenant-premium-{tenant_id}-producer-{uuid.uuid4().hex[:8]}",
)
```

### Quota Testing

Before onboarding high-volume tenants:

1. **Load test with quota limits**
   ```bash
   # Generate test load
   kubectl exec -n kafka redpanda-0 -- \
     rpk topic produce stoa.test.topic \
     --client-id tenant-test \
     --key-count 1000000 \
     --compression none
   ```

2. **Verify throttling behavior**
   ```bash
   # Should see throttle metrics
   kubectl exec -n kafka redpanda-0 -- \
     curl -s http://localhost:9644/metrics | grep throttle
   ```

3. **Measure impact on other tenants**
   - Run concurrent producers for different tenant-ids
   - Verify each tenant operates within their quota
   - Confirm no cross-tenant interference

---

## 6. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | Platform Team | Quota violation detected | Slack `#platform-team` |
| L2 | Platform Lead | Repeated violations or tier upgrade requests | @platform-lead |
| L3 | Sales/Customer Success | Premium tier approval | @sales-team |

---

## 7. Related Documentation

- [Kafka Consumer Lag Runbook](kafka-lag.md)
- [Control Plane API — Kafka Service](../../control-plane-api/src/services/kafka_service.py)
- [Redpanda Quotas Documentation](https://docs.redpanda.com/current/manage/cluster-maintenance/manage-throughput/#quotas)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-20 | Platform Team | Initial creation (CAB-499) |
