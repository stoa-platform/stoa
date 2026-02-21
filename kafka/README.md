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

## Event Backbone Topics (CAB-498)

Three critical topics power STOA's event-driven architecture:

### stoa.audit.events
**Purpose**: Compliance audit trail (SOC2, GDPR, NIS2, DORA)
**SLO**: P95 latency < 500ms
**Retention**: 90 days (configurable up to 5 years for DORA)
**Partitions**: 6 (tenant_id key for isolation)
**Delivery**: exactly_once

**Schema**:
```json
{
  "timestamp": "2026-02-20T14:30:00Z",
  "tenant_id": "tenant-xyz",
  "user_id": "user-123",
  "action": "api.create",
  "resource_type": "api",
  "resource_id": "api-456",
  "request_id": "req-789",
  "ip_address": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "status": "success",
  "error_message": null,
  "metadata": {
    "api_name": "Payment API",
    "gateway_type": "kong"
  }
}
```

**Consumer**: OpenSearch sink (see `kafka/opensearch-connector.yaml`)

### stoa.catalog.changes
**Purpose**: Real-time API catalog synchronization
**SLO**: P95 latency < 2s
**Retention**: 7 days (high-volume, short retention)
**Partitions**: 12 (high parallelism for frequent updates)
**Delivery**: at_least_once

**Schema**:
```json
{
  "timestamp": "2026-02-20T14:30:00Z",
  "tenant_id": "tenant-xyz",
  "event_type": "api.updated",
  "api_id": "api-456",
  "api_name": "Payment API",
  "api_version": "v2.1.0",
  "gateway_id": "gw-kong-prod",
  "spec_hash": "sha256:abc123...",
  "changes": {
    "endpoints": ["+POST /refunds", "-DELETE /legacy"],
    "rate_limit": "100 -> 200 rpm"
  }
}
```

**Consumer**: Control Plane API (drift detection, catalog cache refresh)

### stoa.errors
**Purpose**: Application error tracking and debugging
**SLO**: P95 latency < 1s
**Retention**: 30 days
**Partitions**: 3 (low volume)
**Delivery**: at_least_once

**Schema**:
```json
{
  "timestamp": "2026-02-20T14:30:00Z",
  "tenant_id": "tenant-xyz",
  "error_id": "err-789",
  "service": "control-plane-api",
  "severity": "error",
  "message": "Failed to sync gateway",
  "stack_trace": "Traceback...",
  "request_id": "req-789",
  "gateway_id": "gw-kong-prod",
  "metadata": {
    "gateway_type": "kong",
    "http_status": 500,
    "retry_count": 3
  }
}
```

**Consumer**: Error tracking dashboard, Slack alerts

## Consumer Setup Patterns

### Python (asyncio + aiokafka)

```python
from aiokafka import AIOKafkaConsumer
import json

async def consume_audit_events():
    consumer = AIOKafkaConsumer(
        'stoa.audit.events',
        bootstrap_servers='redpanda.stoa-system.svc.cluster.local:9092',
        group_id='audit-archiver',
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )

    await consumer.start()
    try:
        async for msg in consumer:
            event = msg.value
            await process_audit_event(event)
    finally:
        await consumer.stop()
```

### Go (confluent-kafka-go)

```go
import (
    "github.com/confluentinc/confluent-kafka-go/kafka"
)

func consumeCatalogChanges() {
    c, _ := kafka.NewConsumer(&kafka.ConfigMap{
        "bootstrap.servers": "redpanda.stoa-system.svc.cluster.local:9092",
        "group.id":          "catalog-syncer",
        "auto.offset.reset": "latest",
    })

    c.Subscribe("stoa.catalog.changes", nil)

    for {
        msg, _ := c.ReadMessage(-1)
        processCatalogChange(msg.Value)
    }
}
```

### Rust (rdkafka)

```rust
use rdkafka::consumer::{Consumer, StreamConsumer};
use rdkafka::config::ClientConfig;

async fn consume_errors() {
    let consumer: StreamConsumer = ClientConfig::new()
        .set("bootstrap.servers", "redpanda.stoa-system.svc.cluster.local:9092")
        .set("group.id", "error-tracker")
        .set("auto.offset.reset", "latest")
        .create()
        .expect("Consumer creation failed");

    consumer.subscribe(&["stoa.errors"]).unwrap();

    loop {
        match consumer.recv().await {
            Ok(msg) => process_error(msg.payload().unwrap()),
            Err(e) => eprintln!("Error: {}", e),
        }
    }
}
```

## SLO Monitoring

Event backbone SLOs are monitored via Prometheus recording rules and Grafana dashboards:

- **Prometheus Rules**: `docker/observability/prometheus/rules/kafka-slo.yaml`
- **Grafana Dashboard**: `docker/observability/grafana/dashboards/event-backbone.json`

Key metrics:
- `slo:kafka_audit_producer_latency_p95:seconds` — Audit event producer latency
- `slo:kafka_catalog_producer_latency_p95:seconds` — Catalog event producer latency
- `kafka:audit_consumer_lag:records` — Audit consumer lag
- `slo:kafka_event_backbone:compliance` — Overall SLO compliance score

## References

- [ADR-043: Kafka Event-Driven Architecture](https://docs.gostoa.dev/architecture/adr/adr-043-kafka-mcp-event-bridge)
- [Kafka Lag Runbook](../docs/runbooks/high/kafka-lag.md)
- [Redpanda Documentation](https://docs.redpanda.com/)
