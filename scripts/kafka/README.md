# Kafka/Redpanda Management Scripts

Scripts for managing Kafka/Redpanda configuration and operations.

## configure-quotas.py

Configure multi-tenant quotas to prevent noisy neighbor abuse.

### Usage

```bash
# Apply quotas (standard + premium tiers)
python scripts/kafka/configure-quotas.py \
  --broker redpanda.stoa-system.svc:9092

# Dry run (show what would be done)
python scripts/kafka/configure-quotas.py \
  --broker redpanda.stoa-system.svc:9092 \
  --dry-run

# Verify existing quotas
python scripts/kafka/configure-quotas.py \
  --broker redpanda.stoa-system.svc:9092 \
  --verify-only
```

### Quota Tiers

| Tier | Client ID | Producer | Consumer | CPU |
|------|-----------|----------|----------|-----|
| Standard | `tenant-*` | 10 MB/s | 20 MB/s | 25% |
| Premium | `tenant-premium-*` | 50 MB/s | 100 MB/s | 50% |

### Requirements

```bash
pip install kafka-python
```

### See Also

- [Runbook: Kafka Quota Violation](../../docs/runbooks/high/kafka-quota-violation.md)
- [ADR-043: Kafka Event-Driven Architecture](https://docs.gostoa.dev/architecture/adr/adr-043-kafka-cns)
