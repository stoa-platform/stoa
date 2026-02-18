# Kafka Operations — Topic Management & Configuration

> **Owner**: Platform Team
> **Last updated**: 2026-02-18
> **Related Issues**: CAB-498

---

## Overview

STOA Platform uses Redpanda (Kafka-compatible) for event streaming. This runbook covers topic management, configuration, and operational procedures.

**Cluster Details**:
- **Broker**: redpanda.stoa-system.svc.cluster.local:9092
- **Admin API**: redpanda.stoa-system.svc.cluster.local:9644
- **Tool**: `rpk` (Redpanda CLI)

---

## Topic Inventory (CAB-498)

### Core Sized Topics

| Topic | Partitions | Retention | Compression | Use Case | Producer Config |
|-------|------------|-----------|-------------|----------|-----------------|
| `stoa.audit.trail` | 6 | 90d | lz4 | Compliance audit trail | acks=all, linger.ms=10 |
| `stoa.catalog.sync` | 12 | 7d | snappy | Real-time catalog sync | acks=1, linger.ms=0 |
| `stoa.errors.snapshots` | 3 | 30d | gzip | Detailed error context | acks=all, linger.ms=100 |

### Legacy Topics (Auto-created)

| Topic | Use Case | Retention |
|-------|----------|-----------|
| `stoa.api.lifecycle` | API CRUD events | Default |
| `stoa.deploy.requests` | Gateway deployment queue | Default |
| `stoa.deploy.results` | Deployment results | Default |
| `stoa.tenant.lifecycle` | Tenant provisioning | Default |
| `stoa.gateway.events` | Gateway metrics | Default |
| `stoa.security.alerts` | Security events | Default |

---

## Topic Creation & Configuration

### Prerequisites

Access to Redpanda pod:
```bash
kubectl exec -it -n stoa-system redpanda-0 -- bash
```

### Create Topics (GitOps Method)

The recommended approach is via Kubernetes Job:

```bash
# Apply topic specifications
kubectl apply -f k8s/redpanda/topics.yaml

# Verify ConfigMap
kubectl get configmap kafka-topics-config -n stoa-system

# Run topic creation job (one-time or on-demand)
kubectl create job kafka-topics-init-$(date +%s) \
  --from=cronjob/kafka-topics-init \
  -n stoa-system

# Watch job logs
kubectl logs -n stoa-system -l component=topics-init --follow

# Verify topics created
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic list --brokers redpanda.stoa-system.svc.cluster.local:9092
```

### Manual Topic Creation

If GitOps job fails or for ad-hoc topics:

```bash
# Create audit trail topic (6 partitions, 90d retention)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic create stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --partitions 6 \
    --replicas 1 \
    --config retention.ms=7776000000 \
    --config compression.type=lz4 \
    --config cleanup.policy=delete

# Create catalog sync topic (12 partitions, 7d retention)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic create stoa.catalog.sync \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --partitions 12 \
    --replicas 1 \
    --config retention.ms=604800000 \
    --config compression.type=snappy \
    --config cleanup.policy=delete

# Create error snapshots topic (3 partitions, 30d retention)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic create stoa.errors.snapshots \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --partitions 3 \
    --replicas 1 \
    --config retention.ms=2592000000 \
    --config compression.type=gzip \
    --config cleanup.policy=delete
```

### Topic Configuration Update

```bash
# Update retention policy
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic alter-config stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --set retention.ms=7776000000

# Update compression type
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic alter-config stoa.catalog.sync \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --set compression.type=snappy

# Update cleanup policy
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic alter-config stoa.errors.snapshots \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --set cleanup.policy=delete
```

---

## Topic Inspection

### List Topics

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic list --brokers redpanda.stoa-system.svc.cluster.local:9092
```

### Describe Topic

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092
```

### Check Topic Watermarks (message count)

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.catalog.sync \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --print-datadir
```

### Consume Messages (debugging)

```bash
# Consume latest 10 messages
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --num 10 \
    --format json

# Tail messages (continuous)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.catalog.sync \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --offset end

# Consume from specific partition
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.errors.snapshots \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --partition 0 \
    --offset start
```

---

## Partition Management

### Check Partition Distribution

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.catalog.sync \
    --brokers redpanda.stoa-system.svc.cluster.local:9092
```

### Increase Partitions

**WARNING**: Partition count is **immutable downward**. You can only increase, never decrease without recreating the topic.

```bash
# Increase partitions (example: 12 → 24)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic add-partitions stoa.catalog.sync \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --num 24
```

---

## Consumer Group Management

### List Consumer Groups

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk group list --brokers redpanda.stoa-system.svc.cluster.local:9092
```

### Describe Consumer Group

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk group describe audit-indexer \
    --brokers redpanda.stoa-system.svc.cluster.local:9092
```

### Reset Consumer Group Offset

```bash
# Reset to latest (skip accumulated messages)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk group seek audit-indexer \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --to end

# Reset to earliest (replay all messages)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk group seek audit-indexer \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --to start

# Reset to specific timestamp (Unix ms)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk group seek audit-indexer \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --to-timestamp 1708300800000
```

---

## Producer Configuration

### Recommended Settings by Topic

#### Audit Trail (`stoa.audit.trail`)
```python
producer = KafkaProducer(
    bootstrap_servers='redpanda.stoa-system.svc.cluster.local:9092',
    acks='all',              # Ensure delivery
    linger_ms=10,            # Batch for efficiency
    compression_type='lz4',  # Fast compression
    retries=3,
)
```

#### Catalog Sync (`stoa.catalog.sync`)
```python
producer = KafkaProducer(
    bootstrap_servers='redpanda.stoa-system.svc.cluster.local:9092',
    acks=1,                   # Leader acknowledgment (low latency)
    linger_ms=0,              # No batching (immediate send)
    compression_type='snappy',# Fast compression
    retries=3,
)
```

#### Error Snapshots (`stoa.errors.snapshots`)
```python
producer = KafkaProducer(
    bootstrap_servers='redpanda.stoa-system.svc.cluster.local:9092',
    acks='all',              # Ensure delivery
    linger_ms=100,           # Batch errors
    compression_type='gzip', # High compression for large payloads
    retries=3,
)
```

---

## Monitoring & Alerting

### Key Metrics

| Metric | Threshold | Alert |
|--------|-----------|-------|
| Consumer lag | > 10,000 | High |
| Partition leader changes | > 5/hour | Warning |
| Under-replicated partitions | > 0 | Critical |
| Disk usage | > 80% | Warning |

### Grafana Dashboards

- **Kafka Overview**: https://grafana.gostoa.dev/d/kafka
- **Consumer Lag**: https://grafana.gostoa.dev/d/kafka-lag

### Prometheus Queries

```promql
# Consumer lag by group
kafka_consumer_group_lag{topic="stoa.audit.trail"}

# Messages per second (production rate)
rate(kafka_topic_partition_current_offset[5m])

# Consumer throughput
rate(kafka_consumer_group_offset[5m])
```

---

## Troubleshooting

### Topic Not Found

```bash
# List all topics to verify name
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic list --brokers redpanda.stoa-system.svc.cluster.local:9092

# If missing, recreate from GitOps
kubectl apply -f k8s/redpanda/topics.yaml
kubectl create job kafka-topics-init-$(date +%s) \
  --from=cronjob/kafka-topics-init -n stoa-system
```

### Cannot Produce Messages

```bash
# Check broker health
kubectl exec -n stoa-system redpanda-0 -- \
  rpk cluster health --brokers redpanda.stoa-system.svc.cluster.local:9092

# Check topic config
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe <topic-name> \
    --brokers redpanda.stoa-system.svc.cluster.local:9092

# Test produce
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic produce <topic-name> \
    --brokers redpanda.stoa-system.svc.cluster.local:9092
```

### Consumer Lag Growing

See [Kafka Lag Runbook](high/kafka-lag.md) for detailed diagnosis and resolution.

---

## Retention Policy Management

### Retention Calculation

| Duration | Milliseconds | Days |
|----------|-------------|------|
| 7 days | 604,800,000 | 7 |
| 30 days | 2,592,000,000 | 30 |
| 90 days | 7,776,000,000 | 90 |
| 180 days | 15,552,000,000 | 180 |
| 1 year | 31,536,000,000 | 365 |

### Update Retention

```bash
# Set 90-day retention
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic alter-config stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    --set retention.ms=7776000000

# Verify change
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    | grep retention
```

---

## Backup & Recovery

### Export Topic Configuration

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092 \
    > audit-trail-config.txt
```

### Recreate Topic (Disaster Recovery)

**WARNING**: This deletes all messages. Only for disaster recovery.

```bash
# 1. Delete topic
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic delete stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092

# 2. Recreate from GitOps
kubectl create job kafka-topics-init-$(date +%s) \
  --from=cronjob/kafka-topics-init -n stoa-system

# 3. Verify
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic describe stoa.audit.trail \
    --brokers redpanda.stoa-system.svc.cluster.local:9092
```

---

## Production Deployment Checklist

- [ ] Replication factor set to 3 (HA)
- [ ] Partitions sized for expected load
- [ ] Retention policies configured per compliance requirements
- [ ] Compression type matches use case (lz4/snappy/gzip)
- [ ] Producer acks configured per reliability requirements
- [ ] Consumer groups configured with proper offset management
- [ ] Monitoring dashboards configured
- [ ] Prometheus alerts configured
- [ ] Topic naming follows `stoa.*` convention
- [ ] Documentation updated in this runbook

---

## References

- [Redpanda Documentation](https://docs.redpanda.com/)
- [rpk Commands Reference](https://docs.redpanda.com/current/reference/rpk/)
- [Kafka Producer Config](https://kafka.apache.org/documentation/#producerconfigs)
- [Kafka Consumer Config](https://kafka.apache.org/documentation/#consumerconfigs)
- CAB-498: Topics Kafka STOA — Sizing & Configuration
- [High Consumer Lag Runbook](high/kafka-lag.md)
