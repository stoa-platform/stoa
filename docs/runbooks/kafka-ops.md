# Runbook: Kafka Operations — Topic Management

> **Scope**: Kafka/Redpanda topic lifecycle, configuration, monitoring
> **Last updated**: 2026-02-18
> **Owner**: Platform Team
> **Linear Issue**: CAB-498

---

## 1. Topic Inventory

### Core STOA Topics

| Topic Name | Partitions | Replication | Retention | Use Case | Producer |
|------------|------------|-------------|-----------|----------|----------|
| `stoa.audit.trail` | 6 | 1 (3 in prod) | 90 days | Compliance audit log | Control-Plane API |
| `stoa.catalog.sync` | 12 | 1 (3 in prod) | 7 days | API/MCP lifecycle, gateway sync | Control-Plane API, Gateway |
| `stoa.error.snapshots` | 3 | 1 (3 in prod) | 30 days | Error debugging with full context | All services |

### Legacy Topics (pre-CAB-498)

| Topic Name | Partitions | Retention | Status |
|------------|------------|-----------|--------|
| `stoa.api.lifecycle` | 3 | 7 days | Active (legacy name) |
| `stoa.deploy.requests` | 3 | 7 days | Active |
| `stoa.deploy.results` | 3 | 7 days | Active |
| `stoa.tenant.provisioning` | 3 | 7 days | Active |
| `stoa.workflow.events` | 3 | 7 days | Active |

**Migration note**: Legacy topics use default partitions (3). New topics (CAB-498) use explicit sizing based on expected load.

---

## 2. Topic Naming Convention

**Pattern**: `stoa.<domain>.<event-type>`

### Domains

- `audit` — Compliance and security audit logs
- `catalog` — API/MCP/Tool definitions and lifecycle
- `error` — Error snapshots and debugging
- `deploy` — Deployment orchestration (legacy)
- `tenant` — Tenant provisioning and lifecycle
- `workflow` — Onboarding and workflow automation
- `gateway` — Gateway orchestration and metrics
- `metering` — Usage metering events
- `federation` — Multi-gateway federation

### Event Types

- `trail` — Append-only audit log
- `sync` — State synchronization requests
- `snapshots` — Point-in-time captures
- `requests` — Action requests (command)
- `results` — Action outcomes (event)
- `events` — Generic lifecycle events

---

## 3. Partition Sizing Strategy

| Partition Count | Use Case | Throughput Estimate |
|-----------------|----------|---------------------|
| 3 | Low-volume events (<100 msg/sec) | Errors, tenant events |
| 6 | Medium-volume with tenant isolation | Audit (2 per tier: free/std/ent) |
| 12 | High-volume operational events | Catalog sync (API CRUD + deployments) |

**Key consideration**: Partition count is **immutable** without topic recreation. Start conservative.

**Tenant isolation**: Use tenant_id as partition key to guarantee ordering per tenant.

---

## 4. Retention Policies

| Retention Period | Use Case | Compliance Rationale |
|------------------|----------|---------------------|
| 90 days | Audit trail | GDPR minimum (Article 5) |
| 30 days | Error snapshots | Debugging window (P99 issue resolution) |
| 7 days | Catalog sync | Operational events (no long-term storage need) |

**Compression**: lz4 (audit/errors), snappy (catalog) — balance speed vs ratio.

---

## 5. Creating New Topics

### Prerequisites

- Redpanda cluster accessible (`kubectl exec -n stoa-system redpanda-0`)
- Topic spec documented in `k8s/redpanda/topics.yaml`
- Producer/consumer code updated with new topic constant

### Steps

#### Option A: Via rpk CLI (recommended)

```bash
# 1. Access Redpanda pod
kubectl exec -it -n stoa-system redpanda-0 -- bash

# 2. Create topic with explicit config
rpk topic create stoa.new.topic \
  --brokers=localhost:9092 \
  --partitions=6 \
  --replicas=1 \
  --config retention.ms=604800000 \
  --config compression.type=lz4 \
  --config max.message.bytes=1048576

# 3. Verify creation
rpk topic describe stoa.new.topic --brokers=localhost:9092

# 4. Test produce/consume
echo '{"test": "message"}' | rpk topic produce stoa.new.topic --brokers=localhost:9092
rpk topic consume stoa.new.topic --brokers=localhost:9092 --num=1
```

#### Option B: Via Redpanda Admin API

```bash
# Create topic via HTTP API
kubectl exec -n stoa-system redpanda-0 -- \
  curl -X POST http://localhost:9644/v1/topics \
  -H "Content-Type: application/json" \
  -d '{
    "name": "stoa.new.topic",
    "partitions": 6,
    "replication_factor": 1,
    "configs": {
      "retention.ms": "604800000",
      "compression.type": "lz4"
    }
  }'
```

### Post-Creation Checklist

- [ ] Topic appears in `rpk topic list`
- [ ] Partition count matches spec
- [ ] Retention policy set correctly (`rpk topic describe <name>`)
- [ ] Producer can write test message
- [ ] Consumer can read test message
- [ ] Update `kafka_service.py` Topics class with new constant
- [ ] Document in this runbook

---

## 6. Modifying Topic Configuration

### Mutable Properties (safe to change)

```bash
# Increase retention
rpk topic alter-config stoa.audit.trail --set retention.ms=15552000000

# Change compression
rpk topic alter-config stoa.catalog.sync --set compression.type=zstd

# Update max message size
rpk topic alter-config stoa.error.snapshots --set max.message.bytes=10485760
```

### Immutable Properties (require recreation)

- Partition count (can only increase, never decrease)
- Topic name (must delete and recreate)

**WARNING**: Increasing partitions breaks ordering guarantees. Plan carefully.

---

## 7. Deleting Topics

**DANGER**: Data loss. Always export critical data first.

```bash
# Export topic data before deletion
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.old.topic --format json --num=-1 > backup.jsonl

# Delete topic
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic delete stoa.old.topic --brokers=localhost:9092

# Verify deletion
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic list --brokers=localhost:9092 | grep stoa.old.topic
# Should return nothing
```

---

## 8. Monitoring & Health Checks

### Key Metrics

| Metric | Alert Threshold | Grafana Dashboard |
|--------|----------------|-------------------|
| Consumer lag | > 10,000 messages | [Kafka Dashboard](https://grafana.gostoa.dev/d/kafka) |
| Partition leader distribution | Imbalanced | Redpanda Admin UI |
| Disk usage | > 80% | Node Exporter |
| Message throughput | Sudden drop (< 10 msg/min) | Kafka Dashboard |

### Health Check Commands

```bash
# Cluster health
kubectl exec -n stoa-system redpanda-0 -- rpk cluster health

# Topic list with partition distribution
kubectl exec -n stoa-system redpanda-0 -- rpk topic list --detailed

# Consumer group lag
kubectl exec -n stoa-system redpanda-0 -- rpk group list
kubectl exec -n stoa-system redpanda-0 -- rpk group describe <group-id>

# Broker metrics
kubectl exec -n stoa-system redpanda-0 -- \
  curl -s http://localhost:9644/metrics | grep kafka_
```

---

## 9. Troubleshooting

### Issue: Topic creation fails with "Insufficient brokers"

**Cause**: Replication factor > available brokers.

**Fix**: Reduce replication factor to match broker count (dev: RF=1, prod: RF=3).

```bash
rpk topic create stoa.new.topic --replicas=1  # Single-node cluster
```

### Issue: Consumer lag increasing

**See**: [High Consumer Lag Runbook](./high/kafka-lag.md)

### Issue: Out of disk space

**Symptoms**: `NO_SPACE_LEFT` errors, topic writes failing.

**Fix**:
1. Check disk usage: `kubectl exec -n stoa-system redpanda-0 -- df -h /var/lib/redpanda/data`
2. Reduce retention on high-volume topics
3. Increase PVC size (requires StatefulSet restart)

```bash
# Reduce retention temporarily
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic alter-config stoa.catalog.sync --set retention.ms=86400000  # 1 day
```

### Issue: Partition leader imbalance

**Cause**: Broker restart, uneven load.

**Fix**: Trigger leader election.

```bash
kubectl exec -n stoa-system redpanda-0 -- \
  rpk cluster partitions balancer-status
```

---

## 10. Producer Configuration Guidelines

### Per-Topic Recommendations

| Topic | `acks` | `linger.ms` | `compression.type` | Rationale |
|-------|--------|-------------|-------------------|-----------|
| `stoa.audit.trail` | `all` | 10 | lz4 | Critical data, must not lose |
| `stoa.catalog.sync` | `1` | 5 | snappy | High throughput, leader-only ack |
| `stoa.error.snapshots` | `all` | 50 | gzip | Batch errors, max compression |

### Python (kafka-python) Example

```python
from kafka import KafkaProducer

producer = KafkaProducer(
    bootstrap_servers=['redpanda.stoa-system.svc.cluster.local:9092'],
    acks='all',  # Wait for all replicas (critical topics)
    linger_ms=10,  # Batch window (audit trail)
    compression_type='lz4',
    max_in_flight_requests_per_connection=5,
    enable_idempotence=True,  # Exactly-once semantics
)
```

---

## 11. Consumer Configuration Guidelines

### Best Practices

- `auto.offset.reset=latest` for new deployments (avoid replaying entire history)
- `enable.auto.commit=True` for most use cases
- `session.timeout.ms=30000` + `heartbeat.interval.ms=10000` to avoid rebalancing

### Python (kafka-python) Example

```python
from kafka import KafkaConsumer

consumer = KafkaConsumer(
    'stoa.audit.trail',
    bootstrap_servers=['redpanda.stoa-system.svc.cluster.local:9092'],
    group_id='audit-indexer',
    auto_offset_reset='latest',
    enable_auto_commit=True,
    session_timeout_ms=30000,
    heartbeat_interval_ms=10000,
)
```

---

## 12. Backup & Recovery

### Export Topic Data

```bash
# Full topic export (JSON Lines format)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.audit.trail --format json --num=-1 > audit-backup.jsonl

# Compressed backup
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.audit.trail --format json --num=-1 | gzip > audit-backup.jsonl.gz
```

### Restore Topic Data

```bash
# Restore from backup
gunzip -c audit-backup.jsonl.gz | while read line; do
  echo "$line" | kubectl exec -i -n stoa-system redpanda-0 -- \
    rpk topic produce stoa.audit.trail --brokers=localhost:9092
done
```

---

## 13. Scaling Considerations

### When to increase partitions

- Consumer lag consistently > 10,000
- Single consumer can't keep up with throughput
- Need more parallelism for multi-tenant isolation

**WARNING**: Partition increase is irreversible. Test in staging first.

```bash
# Increase partitions (safe, but breaks ordering)
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic add-partitions stoa.catalog.sync --num=18  # 12 → 18
```

### When to upgrade cluster

Current: Single-node Redpanda (dev/staging)
Upgrade trigger: Production deployment or HA requirement

**Production cluster requirements**:
- 3+ brokers (for RF=3)
- Update `replication_factor: 1 → 3` in topic specs
- Re-create topics with RF=3 (export/import data)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-18 | Platform Team | Initial creation (CAB-498) |
