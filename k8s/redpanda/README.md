# Kafka/Redpanda Topics — STOA Platform

This directory contains Kafka topic specifications and management scripts for the STOA Platform.

## Quick Start

### Prerequisites

- Redpanda StatefulSet deployed: `kubectl apply -f statefulset.yaml`
- Redpanda pod running: `kubectl get pods -n stoa-system -l app=redpanda`

### Create Core Topics (CAB-498)

The 3 core topics are defined in `topics.yaml` ConfigMap:

1. **stoa.audit.trail** — Compliance audit log (6 partitions, 90d retention)
2. **stoa.catalog.sync** — API/MCP lifecycle events (12 partitions, 7d retention)
3. **stoa.error.snapshots** — Error debugging (3 partitions, 30d retention)

#### Option 1: Run creation script from ConfigMap

```bash
# Apply the ConfigMap
kubectl apply -f topics.yaml

# Extract and run the creation script
kubectl get configmap -n stoa-system kafka-topic-specs -o jsonpath='{.data.create-topics\.sh}' | \
  kubectl exec -i -n stoa-system redpanda-0 -- bash

# Expected output:
# Creating STOA Kafka topics...
# TOPIC            STATUS
# stoa.audit.trail       OK
# stoa.catalog.sync      OK
# stoa.error.snapshots   OK
# Topics created successfully.
```

#### Option 2: Manual creation (dev/test)

```bash
# Access Redpanda pod
kubectl exec -it -n stoa-system redpanda-0 -- bash

# Create topics individually
rpk topic create stoa.audit.trail --brokers=localhost:9092 --partitions=6 --replicas=1 \
  --config retention.ms=7776000000 --config compression.type=lz4

rpk topic create stoa.catalog.sync --brokers=localhost:9092 --partitions=12 --replicas=1 \
  --config retention.ms=604800000 --config compression.type=snappy

rpk topic create stoa.error.snapshots --brokers=localhost:9092 --partitions=3 --replicas=1 \
  --config retention.ms=2592000000 --config compression.type=gzip
```

### Verify Topics

```bash
# List all STOA topics
kubectl exec -n stoa-system redpanda-0 -- rpk topic list --brokers=localhost:9092 | grep "^stoa\."

# Detailed info on each topic
kubectl exec -n stoa-system redpanda-0 -- rpk topic describe stoa.audit.trail --brokers=localhost:9092
kubectl exec -n stoa-system redpanda-0 -- rpk topic describe stoa.catalog.sync --brokers=localhost:9092
kubectl exec -n stoa-system redpanda-0 -- rpk topic describe stoa.error.snapshots --brokers=localhost:9092
```

### Smoke Test

Run the automated smoke test to verify all 3 topics are working:

```bash
./scripts/kafka-smoke-test.sh
```

Expected output:
```
==========================================
Kafka Topic Smoke Test (CAB-498)
==========================================

Testing 3 core topics:
  1. stoa.audit.trail (6 partitions, 90d retention)
  2. stoa.catalog.sync (12 partitions, 7d retention)
  3. stoa.error.snapshots (3 partitions, 30d retention)

----------------------------------------
Topic: stoa.audit.trail
----------------------------------------
  Existence check... ✓ Topic exists
  Partition count... ✓ 6 partitions
  Retention policy... ✓ 90d retention
  Produce test... ✓ Message produced
  Consume test... ✓ Message consumed

[... similar for other 2 topics ...]

==========================================
Test Summary
==========================================
Passed: 3/3
Failed: 0

✓ All smoke tests passed
```

## Topic Inventory

### Core Topics (CAB-498)

| Topic | Partitions | Replication | Retention | Compression | Max Message Size | Use Case |
|-------|------------|-------------|-----------|-------------|------------------|----------|
| `stoa.audit.trail` | 6 | 1 | 90 days | lz4 | 1MB | Compliance audit log |
| `stoa.catalog.sync` | 12 | 1 | 7 days | snappy | 2MB | API/MCP lifecycle |
| `stoa.error.snapshots` | 3 | 1 | 30 days | gzip | 5MB | Error debugging |

**Note**: Replication factor = 1 for single-node dev cluster. Increase to 3 for production HA.

### Legacy Topics

See `docs/runbooks/kafka-ops.md` for full topic inventory including legacy topics.

## Configuration Details

### Partition Sizing Rationale

- **6 partitions (audit.trail)**: 2 partitions per tenant tier (free, standard, enterprise) for tenant isolation
- **12 partitions (catalog.sync)**: Highest throughput topic (API CRUD + gateway sync + MCP events)
- **3 partitions (error.snapshots)**: Low volume, partitioned by severity (error/warning/critical)

### Retention Policies

- **90 days (audit.trail)**: GDPR minimum retention for audit logs (Article 5)
- **7 days (catalog.sync)**: Operational events, no long-term storage needed
- **30 days (error.snapshots)**: Debugging window (P99 issue resolution time)

### Producer Recommendations

| Topic | `acks` | `linger.ms` | `compression.type` | Idempotence | Rationale |
|-------|--------|-------------|-------------------|-------------|-----------|
| `audit.trail` | `all` | 10 | lz4 | ✓ | Critical data, no loss tolerance |
| `catalog.sync` | `1` | 5 | snappy | ✓ | High throughput, leader-only ack |
| `error.snapshots` | `all` | 50 | gzip | ✓ | Batch errors, max compression |

See Python example in `control-plane-api/src/services/kafka_service.py`.

## Management Operations

### Modify Retention (safe)

```bash
# Increase audit trail retention to 180 days
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic alter-config stoa.audit.trail --set retention.ms=15552000000
```

### Add Partitions (WARNING: breaks ordering)

```bash
# Increase catalog.sync partitions from 12 to 18
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic add-partitions stoa.catalog.sync --num=18
```

**CAUTION**: Partition count increase is irreversible and breaks per-key ordering guarantees.

### Delete Topic (DANGER: data loss)

```bash
# Backup topic data first
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic consume stoa.old.topic --format json --num=-1 > backup.jsonl

# Delete topic
kubectl exec -n stoa-system redpanda-0 -- \
  rpk topic delete stoa.old.topic --brokers=localhost:9092
```

## Monitoring

### Key Metrics

- **Consumer lag**: Track via `rpk group describe <group-id>`
- **Throughput**: Monitor messages/sec per topic
- **Disk usage**: Alert at 80% capacity (`df -h /var/lib/redpanda/data`)
- **Partition distribution**: Ensure balanced across brokers

### Health Checks

```bash
# Cluster health
kubectl exec -n stoa-system redpanda-0 -- rpk cluster health

# Consumer groups
kubectl exec -n stoa-system redpanda-0 -- rpk group list
kubectl exec -n stoa-system redpanda-0 -- rpk group describe <group-id>
```

## Troubleshooting

### Topics not created

1. Check Redpanda pod logs: `kubectl logs -n stoa-system redpanda-0`
2. Verify broker is healthy: `kubectl exec -n stoa-system redpanda-0 -- rpk cluster health`
3. Check StatefulSet status: `kubectl get statefulset -n stoa-system redpanda`

### Consumer lag increasing

See [High Consumer Lag Runbook](../../docs/runbooks/high/kafka-lag.md) for detailed diagnosis and resolution.

### Out of disk space

1. Check disk usage: `kubectl exec -n stoa-system redpanda-0 -- df -h /var/lib/redpanda/data`
2. Reduce retention temporarily: `rpk topic alter-config <topic> --set retention.ms=86400000`
3. Increase PVC size (requires StatefulSet restart)

## Production Upgrade Checklist

When upgrading from single-node dev to 3-node production cluster:

- [ ] Deploy 3 Redpanda brokers (StatefulSet replicas: 1 → 3)
- [ ] Update topic replication factor: 1 → 3
- [ ] Re-create topics with RF=3 (export/import data if needed)
- [ ] Update `topics.yaml` ConfigMap with `replication_factor: 3`
- [ ] Test failover: kill one broker, verify consumers continue
- [ ] Update monitoring alerts for 3-broker cluster

## References

- [Kafka Operations Runbook](../../docs/runbooks/kafka-ops.md)
- [High Consumer Lag Runbook](../../docs/runbooks/high/kafka-lag.md)
- [Redpanda Documentation](https://docs.redpanda.com/)
- Linear Issue: [CAB-498](https://linear.app/stoa/issue/CAB-498)
