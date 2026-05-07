---
id: plan-2026-05-08-audit-consumer-ingestion-contract
validation_status: draft
source_evidence:
  - docs/audits/2026-05-08-audit-ingestion/findings.md
  - docs/audits/2026-05-08-audit-consumer-restore/scoping.md
---

# Mini-spec — Audit consumer ingestion contract
## Context

PR-1A proved that OVH prod has Kafka topics `stoa.audit.trail` and `audit-log`, but no consumer group subscribed to either. PostgreSQL `audit_events` exists, but the newest observed row was `2026-05-03 20:04:46+00`, with `0` rows in the last 24h.

PR-1A2 proved that the repo contains audit Kafka producers and reusable consumer patterns, but no audit consumer implementation and no deployment manifest to restore. This document defines the missing ingestion contract before any code PR.

This mini-spec is draft until explicitly validated. Do not implement the consumer while `validation_status != validated`.
## Problem

Kafka-only audit emitters publish compliance-relevant events that are not persisted to PostgreSQL `audit_events`, which is the primary source for `/v1/audit/{tenant_id}` and `/audit-log`.

The implementation PR must not invent topic name, payload shape, consumer group, idempotency, retry/DLQ behavior, PostgreSQL semantics, observability, or deployment shape.
## Non-goals
- No Audit Log `/stats` or `/actions` endpoint.
- No actor display, actor resolution, UI refresh/backoff, export, locale, or filter work.
- No `audit_events` schema migration.
- No replacement of existing direct `AuditService.record_event(...)` paths.
- No OpenSearch audit rewrite.
- No deletion, migration, or aliasing of `audit-log` or `stoa.audit.events`.
- No backfill outside retained Kafka messages.
## Canonical producer topic

Canonical source topic:

```text
stoa.audit.trail
```

Evidence: `Topics.AUDIT_LOG = "stoa.audit.trail"` and `KafkaService.emit_audit_event(...)` publishes there. PR-1A also verified the topic exists in prod.

Topic contract:

| Topic | Status |
|---|---|
| `stoa.audit.trail` | Canonical source for this consumer |
| `audit-log` | Runtime topic exists, but no repo producer/consumer found; do not consume first |
| `stoa.audit.events` | Legacy/documented constant; do not consume first |
## Event payload schema

The first implementation must support the current `KafkaService._create_event(...)` envelope. Producer changes are not required.

```json
{
  "id": "uuid-string",
  "type": "audit",
  "source": "control-plane-api",
  "tenant_id": "tenant-id",
  "timestamp": "2026-05-08T12:34:56.000000Z",
  "version": "1.0",
  "user_id": "actor-id-or-null",
  "payload": {
    "action": "api.created",
    "resource_type": "api",
    "resource_id": "resource-id-or-null",
    "details": {}
  }
}
```

Required fields:

| Field | Rule |
|---|---|
| `id` | UUID string; maps to `audit_events.id` |
| `type` | Must equal `audit` |
| `source` | Non-empty; expected `control-plane-api` |
| `tenant_id` | Non-empty; must not be `unknown` |
| `timestamp` | ISO-8601 UTC; maps to `created_at` |
| `version` | Must equal `1.0` |
| `payload.action` | Maps to `action` |
| `payload.resource_type` | Maps to `resource_type` |

Optional compatible fields: `payload.resource_id`, `payload.details`, `payload.method`, `payload.path`, `payload.resource_name`, `payload.outcome`, `payload.status_code`, `payload.actor_email`, `payload.actor_type`, `payload.correlation_id`, `payload.client_ip`, `payload.user_agent`, `payload.diff`, `payload.duration_ms`.

Defaults are allowed only as specified in "PostgreSQL sink contract". Missing required fields go to DLQ.
## Consumer group

Durable consumer group:

```text
audit-trail-pg-consumer
```

Rules:
- Consume only `stoa.audit.trail`.
- Use `auto_offset_reset=earliest` for first deployment because the group is new.
- Disable auto-commit.
- Commit offsets only after PostgreSQL commit, duplicate skip, or successful DLQ publish.
- Do not commit offsets after PostgreSQL outage or DLQ publish failure.
## Idempotency and deduplication

Idempotency key:

```text
Kafka envelope id -> audit_events.id
```

Behavior:
- Successful insert: commit DB transaction, then commit Kafka offset.
- Duplicate `audit_events.id`: treat as success, do not mutate the existing row, then commit offset.
- Invalid UUID `id`: send to DLQ.
- Valid events must not use topic/partition/offset as primary id.
- Add Kafka trace metadata under `details._kafka`: `topic`, `partition`, `offset`, `producer_event_id`, `producer_source`, `producer_version`.
## PostgreSQL sink contract

Sink table: `public.audit_events`. Writes are append-only inserts through `AuditEvent` or a repository wrapper; no update/delete.

Field mapping:

| Column | Mapping |
|---|---|
| `id` | envelope `id` |
| `tenant_id` | envelope `tenant_id` |
| `actor_id` | envelope `user_id` |
| `actor_email` | `payload.actor_email` else `NULL` |
| `actor_type` | `payload.actor_type`, else `user` if `user_id`, else `system` |
| `action` | `payload.action` |
| `method` | `payload.method` else `KAFKA` |
| `path` | `payload.path` else `/events/kafka/stoa.audit.trail/{resource_type}/{action}` |
| `resource_type` | `payload.resource_type` |
| `resource_id` | `payload.resource_id` |
| `resource_name` | `payload.resource_name` else `NULL` |
| `outcome` | `payload.outcome` else `success` |
| `status_code` | `payload.status_code` else `NULL` |
| `client_ip` | `payload.client_ip` else `NULL` |
| `user_agent` | `payload.user_agent` else `NULL` |
| `correlation_id` | `payload.correlation_id`, else `payload.details.correlation_id`, else `NULL` |
| `details` | sanitized `payload.details` plus `details._kafka` |
| `diff` | `payload.diff` else `NULL` |
| `duration_ms` | `payload.duration_ms` else `NULL` |
| `created_at` | envelope `timestamp` |

Validation before insert:
- Non-null: `tenant_id`, `action`, `resource_type`, `method`, `path`, `outcome`, `created_at`.
- `method` must fit 10 chars; `path` must fit 1024 chars.
- `outcome` must be one of `success`, `failure`, `denied`, `error`.
- Kafka offset is committed only after the DB transaction commits.
## Error handling, retries, and DLQ

DLQ topic:

```text
stoa.audit.trail.dlq
```

DLQ message shape:

```json
{
  "source_topic": "stoa.audit.trail",
  "source_partition": 0,
  "source_offset": 123,
  "error_type": "validation_error",
  "error_message": "reason",
  "received_at": "2026-05-08T12:35:10Z",
  "raw_event": {}
}
```

Rules:
- Validation errors go to DLQ once; commit source offset only after DLQ publish succeeds.
- Duplicate primary key is a successful no-op.
- PostgreSQL transient errors roll back, do not commit offset, and retry with exponential backoff capped at 60s.
- PostgreSQL schema/programming errors roll back and do not commit offset; do not DLQ unless the mapper classifies the message as invalid.
- DLQ publish failure means source offset is not committed.
- Auto-commit is forbidden.

Validation errors include missing required fields, `type != "audit"`, unsupported `version`, invalid UUID/timestamp, empty or `unknown` tenant, missing `payload.action` or `payload.resource_type`, invalid `outcome`, and non-object `payload.details`.
## Ordering guarantees

The consumer guarantees Kafka partition order only. There is no global ordering across partitions. `created_at` comes from the producer envelope timestamp, not ingestion time. Backfill can insert older rows after newer rows already exist; readers must continue ordering by `created_at DESC`.
## Tenant isolation and security
- Reject empty or `unknown` `tenant_id`.
- Never infer tenant from resource id, actor id, namespace, or environment.
- Never log full raw payloads at info/warn level.
- Treat DLQ as sensitive internal data because it can include raw events.
- Preserve producer-side masking; run the existing PII/secret masker before writing `details` or prove equivalent sanitization in tests.
- Do not resolve `actor_email` through Keycloak in this consumer.
## Observability

Structured logs must include: `component="audit-trail-consumer"`, topic, partition, offset, event_id, tenant_id, action, resource_type, result, and error_type when applicable.

Required metrics:

```text
stoa_audit_consumer_messages_total{result}
stoa_audit_consumer_processing_seconds_bucket
stoa_audit_consumer_db_errors_total
stoa_audit_consumer_dlq_total{error_type}
stoa_audit_consumer_duplicate_total
stoa_audit_consumer_last_success_timestamp_seconds
```

Allowed `result` labels: `inserted`, `duplicate`, `invalid`, `dlq`, `db_error`, `dlq_error`.

Alert intent:
- consumer group absent in prod after rollout;
- last success older than 15 minutes while source lag is greater than 0;
- DLQ count increases for 5 consecutive minutes.
## Deployment shape

First implementation runs as an in-process Control Plane API background consumer, matching current Kafka-backed consumers.

Required shape:
- New module: `control-plane-api/src/workers/audit_trail_consumer.py`.
- Singleton: `audit_trail_consumer`.
- Startup integration in `control-plane-api/src/main.py`.
- Master gate: `STOA_ENABLE_KAFKA_CONSUMERS`.
- Per-consumer gate: `ENABLE_AUDIT_TRAIL_CONSUMER`, default `true`.
- Topic: `stoa.audit.trail`.
- Group: `audit-trail-pg-consumer`.
- DLQ env override: `AUDIT_TRAIL_DLQ_TOPIC`, default `stoa.audit.trail.dlq`.

Do not add a separate Kubernetes Deployment in the first implementation. Split later only if operational coupling or review size requires it.
## Backfill policy
- First deployment backfills retained `stoa.audit.trail` messages via `auto_offset_reset=earliest`.
- Do not manually seek offsets in code.
- Do not backfill from PostgreSQL, OpenSearch, logs, `audit-log`, or `stoa.audit.events`.
- Do not attempt to recover messages older than Kafka retention.
- Verify backfill with aggregate counts and non-PII samples.
## Rollout plan
1. Add unit tests for schema validation and PostgreSQL mapping.
2. Implement manual-commit consumer and idempotent insert.
3. Add startup gates and extend Kafka boot regression coverage.
4. Run tests with Kafka mocked; no broker required in unit tests.
5. Deploy to dev with `ENABLE_AUDIT_TRAIL_CONSUMER=true`.
6. Produce one controlled audit event through an existing `emit_audit_event(...)` path.
7. Verify `audit_events.details._kafka.producer_event_id`.
8. Verify group `audit-trail-pg-consumer` exists and lag is acceptable.
9. Promote to prod only after dev verification.
10. In prod, verify at least one non-chat audit row appears in `/v1/audit/{tenant_id}` after a manual API mutation.
## Verification plan

Required implementation tests:
- Valid current envelope inserts an `AuditEvent`.
- Missing or `unknown` tenant goes to DLQ.
- Invalid `outcome` goes to DLQ.
- Duplicate `event.id` is a successful no-op.
- PostgreSQL transient error rolls back and does not commit offset.
- DLQ publish failure does not commit offset.
- `STOA_ENABLE_KAFKA_CONSUMERS=false` disables startup.
- `ENABLE_AUDIT_TRAIL_CONSUMER=false` disables startup.
- `git diff --check`.

Runtime verification:

```bash
rpk group describe audit-trail-pg-consumer
rpk topic consume stoa.audit.trail.dlq --num 1 --offset end
```

PostgreSQL aggregate check:

```sql
SELECT action, resource_type, COUNT(*)
FROM audit_events
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY action, resource_type
ORDER BY COUNT(*) DESC;
```

API signal: `GET /v1/audit/{tenant_id}` returns at least one non-`chat_*` row after a controlled Kafka-backed mutation.
## Acceptance criteria
- Implementation consumes only `stoa.audit.trail`.
- Consumer group is exactly `audit-trail-pg-consumer`.
- Consumer uses manual offset commits.
- Valid current envelopes insert into `audit_events`.
- `event.id` is the idempotency key.
- Duplicate messages do not create or mutate rows.
- Invalid messages go to `stoa.audit.trail.dlq`.
- PostgreSQL outages do not commit source offsets.
- Both startup gates disable the consumer.
- `/v1/audit/{tenant_id}` shows at least one non-`chat_*` event after a controlled Kafka-backed audit mutation.
- PR-1B remains blocked until that production signal is observed.
## Open questions
1. Should `audit-log` be deleted, aliased, or retained as unmanaged legacy after the consumer is live?
2. Should `Topics.AUDIT_EVENTS = "stoa.audit.events"` be deprecated or migrated later?
3. Should this consumer move to a dedicated Kubernetes Deployment after initial restore?
4. Should future producers add `method`, `path`, `actor_email`, and `correlation_id` to all audit events?
5. What exact broker retention should `stoa.audit.trail.dlq` use? Minimum recommended retention is 30 days.
