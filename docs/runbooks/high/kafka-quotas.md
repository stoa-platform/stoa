# Kafka Multi-Tenant Quotas — Noisy Neighbor Prevention

## Overview

Kafka quotas prevent "noisy neighbor" scenarios where a single tenant's excessive traffic degrades platform performance for other tenants. STOA implements per-tenant quotas via Redpanda Admin API.

**Quota Tiers**:
- **Standard**: 10 MB/s producer, 20 MB/s consumer, 25% CPU
- **Premium**: 50 MB/s producer, 100 MB/s consumer, 50% CPU

## Architecture

Quotas are enforced at the Redpanda broker level using client-id prefixes:
- Standard tenants: `tenant-standard-{tenant_id}`
- Premium tenants: `tenant-premium-{tenant_id}`

When a tenant exceeds their quota, Redpanda throttles requests (returns `QuotaViolationException` to producers/consumers).

## Apply Quota to New Tenant

```python
from src.services.kafka_quotas import quota_service, TenantTier

# Standard tier
await quota_service.apply_quota("tenant-abc-123", TenantTier.STANDARD)

# Premium tier
await quota_service.apply_quota("tenant-xyz-456", TenantTier.PREMIUM)
```

## Remove Quota

```python
await quota_service.remove_quota("tenant-abc-123", TenantTier.STANDARD)
```

## List All Quotas

```python
quotas = await quota_service.list_quotas()
for quota in quotas:
    print(quota["entity_name"], quota["values"])
```

## Manual Quota Management (via Redpanda Admin API)

### List quotas
```bash
kubectl exec -n stoa-system redpanda-0 -- \
  curl -s http://localhost:9644/v1/kafka_quotas | jq .
```

### Create quota (standard tier example)
```bash
kubectl exec -n stoa-system redpanda-0 -- \
  curl -X POST http://localhost:9644/v1/kafka_quotas \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "client-id",
    "entity_name": "tenant-standard-abc123",
    "values": [
      {"key": "producer_byte_rate", "value": 10485760},
      {"key": "consumer_byte_rate", "value": 20971520},
      {"key": "request_percentage", "value": 25}
    ]
  }'
```

### Delete quota
```bash
kubectl exec -n stoa-system redpanda-0 -- \
  curl -X DELETE "http://localhost:9644/v1/kafka_quotas?entity_type=client-id&entity_name=tenant-standard-abc123"
```

## Monitoring Quota Violations

### Prometheus Metrics

Redpanda exposes quota violation metrics (requires Prometheus scraping):
- `redpanda_kafka_quota_throttled_rate`: Throttled request rate per client
- `redpanda_kafka_request_latency_seconds`: Increased latency indicates throttling

### Alert Example

```yaml
alert: KafkaQuotaViolation
expr: rate(redpanda_kafka_quota_throttled_rate[5m]) > 0
for: 5m
labels:
  severity: warning
annotations:
  summary: "Tenant {{ $labels.client_id }} exceeding Kafka quota"
  description: "Client {{ $labels.client_id }} has been throttled for 5+ minutes. Consider upgrading tier."
```

## Troubleshooting

### Quota not enforced

**Symptom**: Tenant exceeds quota without throttling

**Diagnosis**:
1. Verify quota exists:
   ```bash
   kubectl exec -n stoa-system redpanda-0 -- \
     curl -s http://localhost:9644/v1/kafka_quotas | jq '.[] | select(.entity_name | contains("tenant-abc"))'
   ```
2. Check client is using correct client-id prefix in producer/consumer config:
   ```python
   producer = KafkaProducer(
       client_id="tenant-standard-abc123",  # Must match quota entity_name
       ...
   )
   ```

**Fix**: Ensure client application uses the tenant-prefixed client-id.

### Legitimate traffic throttled

**Symptom**: Tenant reports slow Kafka throughput despite low usage

**Diagnosis**:
1. Check if tenant tier matches their subscription:
   ```python
   quotas = await quota_service.list_quotas()
   # Verify tenant-abc has correct tier (standard vs premium)
   ```
2. Check actual usage vs quota:
   ```bash
   kubectl exec -n stoa-system redpanda-0 -- \
     rpk topic consume stoa.metering.events --format '%v\n' | \
     grep tenant-abc | \
     jq .payload.bytes_sent
   ```

**Fix**: Upgrade tenant to premium tier if usage is legitimate:
```python
await quota_service.remove_quota("tenant-abc", TenantTier.STANDARD)
await quota_service.apply_quota("tenant-abc", TenantTier.PREMIUM)
```

## References

- [Redpanda Quotas Documentation](https://docs.redpanda.com/current/manage/cluster-maintenance/manage-throughput/)
- [Kafka Quotas Design (KIP-13)](https://cwiki.apache.org/confluence/display/KAFKA/KIP-13+-+Quotas)
- CAB-499: Multi-tenant quotas implementation
