# Event Backbone Operations Runbook

> Event-driven architecture for audit, catalog, and error tracking
> Reference: CAB-497, ADR-043

## Overview

The Event Backbone is STOA's Kafka/Redpanda-based event streaming infrastructure that powers:
- **Audit trail** (compliance: SOC2, GDPR, NIS2, DORA)
- **Catalog sync** (real-time API changes)
- **Error tracking** (debugging, alerting)

## Quick Reference

| Component | Endpoint | Purpose |
|-----------|----------|---------|
| Redpanda (Kafka) | `redpanda.stoa-system.svc:9092` | Event streaming broker |
| Redpanda Admin | `redpanda.stoa-system.svc:9644` | Cluster management + metrics |
| Kafka Connect | `kafka-connect.stoa-system.svc:8083` | OpenSearch sink connector |
| Prometheus | `/metrics` on :9644 | Redpanda metrics |
| Grafana | Event Backbone dashboard | SLO monitoring |

## SLO Targets

| Topic | P95 Latency | Retention | Compliance |
|-------|-------------|-----------|------------|
| `stoa.audit.events` | < 500ms | 90d (up to 5yr) | ✓ |
| `stoa.catalog.changes` | < 2s | 7d | - |
| `stoa.errors` | < 1s | 30d | - |

**Overall Availability**: 99.9% (3 9s)

## Common Operations

### Check Cluster Health

```bash
# K8s
kubectl exec -n stoa-system redpanda-0 -- rpk cluster info

# Local
rpk --brokers localhost:9092 cluster info
```

**Expected output**: Cluster ID, broker list, no errors

### List Topics

```bash
kubectl exec -n stoa-system redpanda-0 -- rpk topic list
```

**Key topics to verify**:
- `stoa.audit.events` (6 partitions)
- `stoa.catalog.changes` (12 partitions)
- `stoa.errors` (3 partitions)

### Describe Topic Configuration

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.audit.events --print-configs
```

**Key configs to check**:
- `retention.ms`: matches retention_days policy
- `min.insync.replicas`: 2 (production)
- `replication.factor`: 3 (production), 1 (dev)

### Check Consumer Lag

```bash
# All consumer groups
kubectl exec -n stoa-system redpanda-0 -- rpk group list

# Specific group lag
kubectl exec -n stoa-system redpanda-0 -- \
  rpk group describe audit-archiver
```

**Alert thresholds**:
- Audit lag > 10,000 records → P2 (investigate)
- Audit lag > 50,000 records → P1 (critical)
- Catalog lag > 100,000 records → P2

### Produce Test Message

```bash
echo '{"test":"manual","timestamp":"'$(date -Iseconds)'"}' | \
  kubectl exec -i -n stoa-system redpanda-0 -- \
    rpk topic produce stoa.audit.events
```

### Consume Recent Messages

```bash
# Last 10 messages
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.audit.events --num 10 --offset end

# Follow (tail -f mode)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.audit.events --offset end
```

### Run Smoke Tests

```bash
# K8s deployment
cd kafka && ./smoke-test.sh k8s

# Local development
cd kafka && ./smoke-test.sh local
```

## Monitoring & Alerting

### Grafana Dashboard

**Dashboard**: Event Backbone - Kafka/Redpanda
**Location**: `docker/observability/grafana/dashboards/event-backbone.json`

**Key panels**:
1. SLO Compliance Overview (stat)
2. Producer Latency SLOs (timeseries)
3. Consumer Lag (timeseries)
4. Event Production Rate (timeseries)
5. Redpanda Cluster Health (stat)

### Prometheus Queries

```promql
# Overall SLO compliance score
slo:kafka_event_backbone:compliance

# Audit event latency
slo:kafka_audit_producer_latency_p95:seconds

# Consumer lag
kafka:audit_consumer_lag:records

# Under-replicated partitions (should be 0)
redpanda:under_replicated_partitions:count

# Event production rate
kafka:messages_produced:rate
```

### Alert Rules

**Critical (P1)**:
- Audit consumer lag > 50,000 records for 15 min
- Audit SLO breach (P95 > 500ms) for 10 min
- Under-replicated partitions > 0 for 5 min
- Produce success rate < 99% for 5 min

**Warning (P2)**:
- Audit consumer lag > 10,000 records for 30 min
- Catalog SLO breach (P95 > 2s) for 15 min
- ISR shrinks rate > 10/min

## Troubleshooting

### High Consumer Lag

**Symptoms**: `kafka:audit_consumer_lag:records` > 10,000

**Root causes**:
1. Consumer group down/paused
2. Slow consumer processing (OpenSearch backpressure)
3. High message production rate

**Resolution**:
```bash
# Check consumer group status
kubectl exec -n stoa-system redpanda-0 -- \
  rpk group describe audit-archiver

# If stuck, reset offsets (CAUTION: may lose messages)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk group seek audit-archiver --to end --topic stoa.audit.events

# Scale up consumer pods (if applicable)
kubectl scale deployment kafka-connect-opensearch --replicas=3 -n stoa-system
```

### SLO Breach (High Latency)

**Symptoms**: `slo:kafka_audit_producer_latency_p95:seconds` > 0.5

**Root causes**:
1. Redpanda pod resource exhaustion (CPU/memory)
2. Disk I/O saturation (PVC)
3. Network latency (control plane → Redpanda)

**Resolution**:
```bash
# Check pod resources
kubectl top pod redpanda-0 -n stoa-system

# Check disk usage
kubectl exec -n stoa-system redpanda-0 -- df -h /var/lib/redpanda

# Increase resources (if needed)
kubectl edit statefulset redpanda -n stoa-system
# Update requests/limits under spec.template.spec.containers[0].resources

# Restart pod (last resort)
kubectl delete pod redpanda-0 -n stoa-system
```

### Under-Replicated Partitions

**Symptoms**: `redpanda:under_replicated_partitions:count` > 0

**Root causes**:
1. Broker restart/failure
2. Network partition
3. Replication lag

**Resolution**:
```bash
# Check cluster status
kubectl exec -n stoa-system redpanda-0 -- rpk cluster info

# Check partition status
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.audit.events

# Force leader election (if stuck)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk cluster maintenance enable redpanda-0
sleep 10
kubectl exec -n stoa-system redpanda-0 -- \
  rpk cluster maintenance disable redpanda-0
```

### OpenSearch Connector Failure

**Symptoms**: Audit events not in OpenSearch, connector status unhealthy

**Root causes**:
1. OpenSearch unreachable
2. Invalid credentials
3. Index mapping conflict

**Resolution**:
```bash
# Check connector status
kubectl exec -n stoa-system kafka-connect-0 -- \
  curl -s http://localhost:8083/connectors/opensearch-audit-sink/status

# Restart connector
kubectl delete pod kafka-connect-opensearch-0 -n stoa-system

# Check OpenSearch reachability
kubectl exec -n stoa-system kafka-connect-0 -- \
  curl -s -u admin:PASSWORD https://opensearch.stoa-system.svc:9200/_cluster/health

# Re-apply index template (if mapping conflict)
kubectl apply -f kafka/opensearch-connector.yaml
```

## Maintenance

### Create New Topic

1. Edit `kafka/topic-policies.yaml`:
```yaml
stoa.new.topic:
  delivery: at_least_once
  retention_days: 30
  partitions: 6
  key: tenant_id
  description: New event type
```

2. Create topic:
```bash
cd kafka && ./create-topics.sh
```

3. Verify:
```bash
./verify-topics.sh
```

### Update Topic Retention

```bash
# Change retention to 180 days (example: extending audit retention for DORA)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic alter-config stoa.audit.events \
    --set retention.ms=$((180 * 24 * 60 * 60 * 1000))

# Verify
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.audit.events --print-configs | grep retention
```

### Scale Partitions (Irreversible)

**Warning**: Cannot reduce partitions, only increase.

```bash
# Increase catalog partitions from 12 to 24 (for higher throughput)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic add-partitions stoa.catalog.changes --num 24

# Rebalance consumers after partition increase
kubectl rollout restart deployment catalog-consumer -n stoa-system
```

### Backup Topics (Manual Snapshot)

```bash
# Export topic data
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.audit.events \
    --offset start \
    --format json > audit-backup-$(date +%Y%m%d).jsonl

# Compress
gzip audit-backup-*.jsonl
```

### Restore from Backup

```bash
# Restore messages (example: audit events)
gunzip -c audit-backup-20260220.jsonl.gz | \
  kubectl exec -i -n stoa-system redpanda-0 -- \
    rpk topic produce stoa.audit.events --format json
```

## References

- [Kafka Topic Policies](../kafka/topic-policies.yaml)
- [Event Backbone README](../kafka/README.md)
- [ADR-043: Kafka Event-Driven Architecture](https://docs.gostoa.dev/architecture/adr/adr-043-kafka-mcp-event-bridge)
- [Kafka Lag Runbook](./high/kafka-lag.md)
- [Redpanda Documentation](https://docs.redpanda.com/)
