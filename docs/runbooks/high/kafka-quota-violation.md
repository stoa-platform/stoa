# Runbook: Kafka/Redpanda - Quota Violation (Noisy Neighbor)

> **Severity**: High
> **Last updated**: 2026-02-20
> **Owner**: Platform Team
> **Linear Issue**: CAB-499

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `KafkaQuotaViolation` | `kafka_quota_throttle_time > 0` | [Kafka Dashboard](https://grafana.gostoa.dev/d/kafka) |
| `KafkaTenantThrottled` | `kafka_produce_throttle_time_ms{client_id=~"tenant-.*"} > 100` | [Multi-tenant](https://grafana.gostoa.dev/d/multi-tenant) |
| `KafkaProducerBlocked` | Producer send fails with QuotaViolationError | Application logs |

### Observed Behavior

- Tenant API calls failing with 429 (quota exceeded)
- Kafka producer errors: "QuotaViolationError"
- Increased latency for other tenants (noisy neighbor)
- Kafka broker throttling specific clients

### Business Impact

| Impact | Description |
|--------|-------------|
| **Single Tenant** | One tenant's excessive usage blocked |
| **Multi-tenant** | Other tenants protected from noisy neighbor |
| **SLA** | Fair usage policy enforced, prevents platform abuse |

---

## 2. Multi-Tenant Quota Policies

### Quota Tiers

| Tier | Client ID Pattern | Producer | Consumer | CPU | Use Case |
|------|------------------|----------|----------|-----|----------|
| **Standard** | `tenant-*` | 10 MB/s | 20 MB/s | 25% | Default for all tenants |
| **Premium** | `tenant-premium-*` | 50 MB/s | 100 MB/s | 50% | Enterprise customers |

### How Quotas Work

- **Producer byte rate**: Max bytes/sec a tenant can produce to Kafka
- **Consumer byte rate**: Max bytes/sec a tenant can consume from Kafka
- **Request percentage**: Max % of broker CPU a tenant can use (prevents request spam)

Client ID naming:
- Standard: `tenant-{tenant_id}` (e.g., `tenant-acme`)
- Premium: `tenant-premium-{tenant_id}` (e.g., `tenant-premium-bigcorp`)

---

## 3. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check quota violations
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe --client-id tenant-*

kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe --client-id tenant-premium-*

# 2. Check throttled clients
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster logdirs describe | grep -i throttle

# 3. Check Kafka logs for quota violations
kubectl logs -n kafka redpanda-0 --tail=100 | grep -i quota

# 4. Check producer metrics
kubectl exec -n stoa-system deploy/control-plane-api -- \
  curl -s localhost:8000/metrics | grep kafka_producer
```

### Verification Points

- [ ] Quota policies configured?
- [ ] Which tenant is hitting quota?
- [ ] Is it a legitimate spike or abuse?
- [ ] Are other tenants affected?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Legitimate traffic spike | High | Check tenant usage trends |
| Inefficient producer (small batches) | Medium | Check producer batch size |
| Retry loop (failing sends) | Medium | Check error logs |
| Malicious abuse | Low | Check rate of increase |
| Wrong quota tier (standard vs premium) | Low | Check client_id pattern |

---

## 4. Resolution

### Immediate Action (mitigation)

```bash
# 1. Identify throttled tenant
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe --client-id tenant-* | grep -A5 "throttle"

# 2. Check if tenant should be premium tier
# If yes, update client_id in Control Plane API:
# Change "tenant-acme" to "tenant-premium-acme"

# 3. Temporary quota increase (emergency only)
# See "Case 3: Emergency quota increase" below
```

### Resolution by Cause

#### Case 1: Legitimate traffic spike

```bash
# Option A: Upgrade to premium tier
# Update tenant's client_id prefix in Control Plane API database:
kubectl exec -n stoa-system deploy/postgres -- \
  psql -U stoa -d stoa_platform -c \
  "UPDATE tenants SET kafka_client_id = 'tenant-premium-acme' WHERE id = 'acme';"

# Restart API to pick up new client_id
kubectl rollout restart deployment -n stoa-system control-plane-api

# Option B: Optimize producer (batch more, compress)
# Check producer config in Control Plane API
kubectl logs -n stoa-system deploy/control-plane-api | grep kafka_producer
```

#### Case 2: Inefficient producer

```bash
# Check producer batch size and compression
kubectl exec -n stoa-system deploy/control-plane-api -- \
  python -c "
from src.services.kafka_service import kafka_service
print('Batch size:', kafka_service._producer.config.get('batch_size'))
print('Compression:', kafka_service._producer.config.get('compression_type'))
"

# Recommended producer settings:
# batch_size: 16384 (16KB)
# linger_ms: 10
# compression_type: snappy or lz4
```

#### Case 3: Emergency quota increase

```bash
# WARNING: Only use if tenant needs immediate relief and upgrade is justified

# Manually increase quota (not persistent)
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas alter --client-id tenant-acme \
  --producer-byte-rate 20971520 \
  --consumer-byte-rate 41943040 \
  --request-percentage 40

# Verify new quota
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe --client-id tenant-acme

# IMPORTANT: Update quota config file for persistence
# Edit scripts/kafka/configure-quotas.py or apply via ConfigMap
```

#### Case 4: Retry loop (producer failing)

```bash
# Check for repeated send failures
kubectl logs -n stoa-system deploy/control-plane-api --tail=100 | \
  grep -i "failed to publish\|KafkaError" | wc -l

# If high count, check broker health
kubectl exec -n kafka redpanda-0 -- rpk cluster health

# Fix underlying issue (broker down, network, etc.)
# Producer will stop retrying once sends succeed
```

#### Case 5: Investigate potential abuse

```bash
# Check tenant's usage pattern
kubectl logs -n stoa-system deploy/control-plane-api | \
  grep "tenant_id=acme" | \
  awk '{print $1}' | uniq -c

# Check what topics they're producing to
kubectl exec -n kafka redpanda-0 -- \
  rpk topic consume stoa.audit.trail --num 100 --format json | \
  jq 'select(.tenant_id == "acme") | .type' | sort | uniq -c

# If abuse confirmed, temporarily suspend tenant
kubectl exec -n stoa-system deploy/postgres -- \
  psql -U stoa -d stoa_platform -c \
  "UPDATE tenants SET status = 'suspended' WHERE id = 'acme';"
```

---

## 5. Post-Resolution Verification

### Validation Checklist

- [ ] Tenant no longer throttled
- [ ] No QuotaViolationError in logs
- [ ] Other tenants unaffected
- [ ] Quota settings persisted
- [ ] Alert resolved

### Verification Commands

```bash
# Check quota status
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas describe --client-id tenant-acme

# Verify no throttling
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster logdirs describe | grep tenant-acme

# Check producer is working
kubectl logs -n stoa-system deploy/control-plane-api --tail=50 | \
  grep "Published.*tenant_id=acme"
```

---

## 6. Quota Configuration

### Apply Quotas (Initial Setup)

```bash
# From project root
cd control-plane-api
python ../scripts/kafka/configure-quotas.py \
  --broker redpanda.stoa-system.svc:9092

# Dry run first
python ../scripts/kafka/configure-quotas.py \
  --broker redpanda.stoa-system.svc:9092 \
  --dry-run

# Verify applied
python ../scripts/kafka/configure-quotas.py \
  --broker redpanda.stoa-system.svc:9092 \
  --verify-only
```

### Modify Quotas

```bash
# Edit quota values in scripts/kafka/configure-quotas.py
# Then reapply:
python scripts/kafka/configure-quotas.py \
  --broker redpanda.stoa-system.svc:9092

# Or use rpk directly for one-off changes:
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas alter --client-id tenant-premium-* \
  --producer-byte-rate 52428800 \
  --consumer-byte-rate 104857600 \
  --request-percentage 50
```

### Remove Quotas (Caution)

```bash
# Remove quota for a specific client
kubectl exec -n kafka redpanda-0 -- \
  rpk cluster quotas delete --client-id tenant-test

# WARNING: Do not remove wildcard quotas (tenant-*, tenant-premium-*)
# They protect the platform from noisy neighbors
```

---

## 7. Monitoring & Alerting

### Recommended Prometheus Alerts

```yaml
groups:
  - name: kafka-quotas
    rules:
      - alert: KafkaQuotaViolation
        expr: kafka_quota_throttle_time > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Kafka client {{ $labels.client_id }} is being throttled"

      - alert: KafkaTenantThrottled
        expr: kafka_produce_throttle_time_ms{client_id=~"tenant-.*"} > 100
        for: 10m
        labels:
          severity: high
        annotations:
          summary: "Tenant {{ $labels.client_id }} hitting quota limits"

      - alert: KafkaQuotaMisconfigured
        expr: absent(kafka_quota_producer_byte_rate{client_id="tenant-*"})
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Kafka quotas not configured"
```

### Key Metrics

- `kafka_quota_producer_byte_rate`: Current producer quota (bytes/sec)
- `kafka_quota_consumer_byte_rate`: Current consumer quota (bytes/sec)
- `kafka_quota_request_percentage`: Current CPU quota (%)
- `kafka_produce_throttle_time_ms`: Time producer was throttled
- `kafka_fetch_throttle_time_ms`: Time consumer was throttled

---

## 8. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | If tenant blocked > 15min | Slack `#platform-team` |
| L3 | Customer Success | If premium customer affected | @cs-team |

---

## 9. Prevention

### Best Practices

1. **Set default quotas** for all new tenants (via client_id pattern)
2. **Monitor quota usage** per tenant
3. **Alert on sustained throttling** (not transient spikes)
4. **Upgrade to premium proactively** for high-volume customers
5. **Review quota tiers quarterly** based on usage trends

### Quota Planning

| Tenant Type | Expected Traffic | Recommended Tier |
|-------------|-----------------|------------------|
| Free trial | < 1 MB/s | Standard (10/20 MB/s) |
| Paid SMB | 1-10 MB/s | Standard (10/20 MB/s) |
| Enterprise | 10-50 MB/s | Premium (50/100 MB/s) |
| Very high volume | > 50 MB/s | Custom quota + dedicated cluster |

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-20 | AI Factory | Initial creation (CAB-499) |
