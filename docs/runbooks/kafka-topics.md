# Runbook: Kafka Topic Management

> **Last updated**: 2026-02-20
> **Owner**: Platform Team
> **Linear Issue**: CAB-498

---

## Overview

STOA Platform uses Kafka/Redpanda for event-driven architecture. All topics follow the `stoa.*` naming convention and are configured declaratively in `kafka/topic-policies.yaml`.

## Topic Inventory

### New Topics (CAB-498)

| Topic | Partitions | Retention | RF | Use Case |
|-------|-----------|-----------|-----|----------|
| `stoa.audit.events` | 6 | 90d | 3 | Detailed audit events for compliance tracking |
| `stoa.catalog.changes` | 12 | 7d | 3 | API catalog sync events and schema changes (high-volume) |
| `stoa.errors` | 3 | 30d | 3 | Application error tracking and debugging events |

### Key Configuration

- **Replication Factor (RF)**: 3 (all topics)
- **min.insync.replicas**: 2 (ensures durability)
- **Partition key**: `tenant_id` (ensures ordering per tenant)
- **Delivery semantics**:
  - `exactly_once`: audit.events (compliance)
  - `at_least_once`: catalog.changes, errors (standard)

## Creating Topics

### Prerequisites

```bash
# Install dependencies
pip install pyyaml kafka-python

# Or use system package manager
brew install python3 pyyaml  # macOS
apt-get install python3-yaml # Ubuntu
```

### Local Kafka/Redpanda

```bash
cd kafka/

# Dry-run (preview)
./create-topics.sh dry-run

# Create topics
./create-topics.sh

# Or using Python directly
python3 create-topics.py --broker localhost:9092
```

### Kubernetes (Production)

```bash
cd kafka/

# Set environment
export KAFKA_NAMESPACE=kafka
export REDPANDA_POD=redpanda-0

# Dry-run
./create-topics.sh dry-run

# Create topics
./create-topics.sh
```

### Manual Creation (rpk)

For individual topic creation:

```bash
# stoa.audit.events
kubectl exec -n kafka redpanda-0 -- \
  rpk topic create stoa.audit.events \
  --partitions 6 \
  --replicas 3 \
  --config retention.ms=7776000000 \
  --config min.insync.replicas=2

# stoa.catalog.changes
kubectl exec -n kafka redpanda-0 -- \
  rpk topic create stoa.catalog.changes \
  --partitions 12 \
  --replicas 3 \
  --config retention.ms=604800000 \
  --config min.insync.replicas=2

# stoa.errors
kubectl exec -n kafka redpanda-0 -- \
  rpk topic create stoa.errors \
  --partitions 3 \
  --replicas 3 \
  --config retention.ms=2592000000 \
  --config min.insync.replicas=2
```

## Verification

### Automated Verification

```bash
cd kafka/
./verify-topics.sh
```

Expected output:
```
STOA Kafka Topic Verification
==============================

Checking topics...

stoa.audit.events                        ✓ OK (partitions: 6)
stoa.catalog.changes                     ✓ OK (partitions: 12)
stoa.errors                              ✓ OK (partitions: 3)

Summary:
--------
Total topics: 3
OK: 3
Mismatches: 0
Missing: 0
```

### Manual Verification

```bash
# List all topics
kubectl exec -n kafka redpanda-0 -- rpk topic list

# Describe specific topics
kubectl exec -n kafka redpanda-0 -- rpk topic describe stoa.audit.events
kubectl exec -n kafka redpanda-0 -- rpk topic describe stoa.catalog.changes
kubectl exec -n kafka redpanda-0 -- rpk topic describe stoa.errors

# Check partitions and config
kubectl exec -n kafka redpanda-0 -- \
  rpk topic describe stoa.audit.events --print-configs
```

Expected output:
```
NAME              stoa.audit.events
PARTITIONS        6
REPLICAS          3
...
CONFIGS
  retention.ms    7776000000  # 90 days
  min.insync.replicas  2
```

## Troubleshooting

### Topic Creation Failed

**Symptom**: `create-topics.sh` exits with error

**Common causes**:
1. Redpanda pod not running
2. Insufficient brokers for RF=3
3. Topic already exists

**Resolution**:
```bash
# Check Redpanda health
kubectl exec -n kafka redpanda-0 -- rpk cluster health

# Check existing topics
kubectl exec -n kafka redpanda-0 -- rpk topic list

# Delete topic if needed (WARNING: data loss)
kubectl exec -n kafka redpanda-0 -- rpk topic delete <topic-name>

# Retry creation
./create-topics.sh
```

### Partition Count Mismatch

**Symptom**: `verify-topics.sh` shows mismatch

**Cause**: Topic created with wrong partition count

**Resolution**:
```bash
# Increase partitions (irreversible)
kubectl exec -n kafka redpanda-0 -- \
  rpk topic alter-config stoa.catalog.changes --set partition.count=12

# Verify
kubectl exec -n kafka redpanda-0 -- rpk topic describe stoa.catalog.changes
```

**Note**: Decreasing partitions is NOT supported. Must delete and recreate topic (data loss).

### Retention Not Applied

**Symptom**: Messages deleted before retention period

**Resolution**:
```bash
# Check current retention
kubectl exec -n kafka redpanda-0 -- \
  rpk topic describe stoa.audit.events --print-configs | grep retention.ms

# Update retention (90 days = 7776000000 ms)
kubectl exec -n kafka redpanda-0 -- \
  rpk topic alter-config stoa.audit.events --set retention.ms=7776000000

# Verify
kubectl exec -n kafka redpanda-0 -- \
  rpk topic describe stoa.audit.events --print-configs
```

## Adding New Topics

1. Edit `kafka/topic-policies.yaml`:

```yaml
topics:
  stoa.new.topic:
    delivery: at_least_once
    retention_days: 30
    partitions: 6
    key: tenant_id
    description: New topic description
```

2. Update `control-plane-api/src/services/kafka_service.py`:

```python
class Topics:
    # ...
    NEW_TOPIC = "stoa.new.topic"
```

3. Create the topic:

```bash
cd kafka/
./create-topics.sh
```

4. Verify:

```bash
./verify-topics.sh
```

## Monitoring

### Key Metrics

| Metric | Alert Threshold | Dashboard |
|--------|----------------|-----------|
| Consumer lag | > 10000 | [Kafka Dashboard](https://grafana.gostoa.dev/d/kafka) |
| Disk usage | > 80% | [Kafka Dashboard](https://grafana.gostoa.dev/d/kafka) |
| Replication lag | > 1000 | [Kafka Dashboard](https://grafana.gostoa.dev/d/kafka) |

### Health Check

```bash
# Cluster health
kubectl exec -n kafka redpanda-0 -- rpk cluster health

# Topic status
kubectl exec -n kafka redpanda-0 -- rpk topic list

# Consume test
kubectl exec -n kafka redpanda-0 -- \
  rpk topic consume stoa.audit.events --num 1 --format json
```

## Files

| File | Purpose |
|------|---------|
| `kafka/topic-policies.yaml` | Declarative topic configuration (source of truth) |
| `kafka/create-topics.sh` | Shell script to create topics from YAML |
| `kafka/create-topics.py` | Python script for programmatic topic creation |
| `kafka/verify-topics.sh` | Verification script to check topic configuration |
| `control-plane-api/src/services/kafka_service.py` | Topics class with topic name constants |

## References

- [ADR-043: Kafka Event-Driven Architecture](../../stoa-docs/docs/architecture/adr/adr-043-kafka-mcp-event-bridge.md)
- [Kafka Lag Runbook](./high/kafka-lag.md)
- [Redpanda Documentation](https://docs.redpanda.com/)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-20 | Platform Team | Initial creation (CAB-498) |
