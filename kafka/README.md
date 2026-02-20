# STOA Kafka Topic Management

Declarative Kafka/Redpanda topic configuration for the STOA Platform.

## Quick Start

```bash
# Preview topics that will be created
./create-topics.sh dry-run

# Create all topics
./create-topics.sh

# Verify topics
./verify-topics.sh
```

## Files

| File | Purpose |
|------|---------|
| `topic-policies.yaml` | **Source of truth** - Declarative topic configuration |
| `create-topics.sh` | Shell script to create topics (uses rpk for Redpanda) |
| `create-topics.py` | Python script for programmatic topic creation |
| `verify-topics.sh` | Verification script to check topic configuration |
| `README.md` | This file |

## Topic Schema

Each topic in `topic-policies.yaml` follows this structure:

```yaml
stoa.topic.name:
  delivery: at_least_once | exactly_once
  retention_days: 30  # -1 for infinite
  partitions: 6       # Number of partitions
  key: tenant_id      # Partition key field
  description: Topic description
```

### Configuration Values

- **delivery**: `at_least_once` (standard) or `exactly_once` (compliance/audit)
- **retention_days**: How long to keep messages (-1 = infinite for audit/compliance)
- **partitions**: Number of partitions (higher = more parallelism, higher volume)
- **key**: Field used for partitioning (usually `tenant_id` for tenant isolation)
- **Replication factor**: Always 3 (hardcoded for production durability)
- **min.insync.replicas**: Always 2 (ensures writes to at least 2 replicas)

### Partition Guidelines

| Volume | Partitions | Examples |
|--------|-----------|----------|
| Low | 3 | MCP, gateway events, app lifecycle |
| Medium | 6 | API lifecycle, deployments, audit |
| High | 12 | Metrics, catalog changes (frequent updates) |

## Adding a New Topic

1. Edit `topic-policies.yaml`:

```yaml
stoa.new.topic:
  delivery: at_least_once
  retention_days: 30
  partitions: 6
  key: tenant_id
  description: Your topic description
```

2. Update `control-plane-api/src/services/kafka_service.py`:

```python
class Topics:
    # ...
    NEW_TOPIC = "stoa.new.topic"
```

3. Create the topic:

```bash
./create-topics.sh
./verify-topics.sh
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BROKER` | `localhost:9092` | Kafka bootstrap server |
| `REDPANDA_POD` | `redpanda-0` | Kubernetes pod name |
| `KAFKA_NAMESPACE` | `kafka` | Kubernetes namespace |

## Manual Topic Creation

If you need to create a single topic manually:

```bash
# Local Redpanda
rpk topic create stoa.topic.name \
  --brokers localhost:9092 \
  --partitions 6 \
  --replicas 3 \
  --config retention.ms=2592000000 \
  --config min.insync.replicas=2

# Kubernetes
kubectl exec -n kafka redpanda-0 -- \
  rpk topic create stoa.topic.name \
  --partitions 6 \
  --replicas 3 \
  --config retention.ms=2592000000 \
  --config min.insync.replicas=2
```

### Retention Conversion

| Days | Milliseconds |
|------|-------------|
| 1 | 86400000 |
| 7 | 604800000 |
| 30 | 2592000000 |
| 90 | 7776000000 |
| -1 | -1 (infinite) |

## Verification

```bash
# List all topics
kubectl exec -n kafka redpanda-0 -- rpk topic list

# Describe a topic
kubectl exec -n kafka redpanda-0 -- rpk topic describe stoa.audit.events

# Show configuration
kubectl exec -n kafka redpanda-0 -- \
  rpk topic describe stoa.audit.events --print-configs
```

## Troubleshooting

See the [Kafka Topic Management Runbook](../docs/runbooks/kafka-topics.md) for detailed troubleshooting steps.

## References

- [ADR-043: Kafka Event-Driven Architecture](https://docs.gostoa.dev/architecture/adr/adr-043-kafka-mcp-event-bridge)
- [Kafka Lag Runbook](../docs/runbooks/high/kafka-lag.md)
- [Redpanda Documentation](https://docs.redpanda.com/)
