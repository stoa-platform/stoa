# PR-1A2 - Audit Consumer Restore Scoping

Generated: 2026-05-07

Scope: repository discovery only. No runtime state, source code, workflow, deployment manifest, database schema, or Kubernetes resource was modified.

## Verdict

**CONSUMER_IMPLEMENTATION_NOT_FOUND**

The repository contains Kafka audit producers and generic Kafka consumer patterns, but no audit consumer implementation that persists `stoa.audit.trail`, `audit-log`, or `stoa.audit.events` into PostgreSQL `audit_events`.

Because there is no existing implementation or deployment manifest to restore, this PR must stay as a scoping PR. PR-1B remains blocked until the audit ingestion contract is explicitly designed and validated.

## Discovery Commands

```bash
rg -n "audit_events|stoa\.audit\.trail|audit-log|audit-events|audit consumer|AuditConsumer|consumer group|kafka_service\.emit_audit_event|emit_audit_event" .
rg -n "KafkaConsumer|AIOKafkaConsumer|create_consumer|consume\(|consumer_group|group_id|group.id|subscribe\(|Topics\.AUDIT_LOG|AUDIT_LOG" control-plane-api charts deploy .github docs scripts stoa-gateway stoa-go cli
rg -n "stoa\.audit\.events|Topics\.AUDIT_EVENTS|AUDIT_EVENTS|audit\.events|audit-events-consumer|audit-events" control-plane-api/src control-plane-api/tests charts deploy docs .github
rg -n "ENABLE_.*CONSUMER|STOA_ENABLE_KAFKA_CONSUMERS|KAFKA_BOOTSTRAP_SERVERS|security-alert-consumer|billing-metering-consumer|chat-metering-consumer|deployment-notification-consumer|git-sync-worker" control-plane-api/k8s deploy/config charts/stoa-platform .github/workflows/control-plane-api-ci.yml
```

## Repository Facts

### Kafka audit producers exist

- `control-plane-api/src/services/kafka_service.py` defines `Topics.AUDIT_LOG = "stoa.audit.trail"`.
- `KafkaService.emit_audit_event(...)` publishes event type `audit` to `Topics.AUDIT_LOG`.
- Existing emit sites include deployment, promotion, API, tenant, and user flows, as already inventoried in `docs/audits/2026-05-08-audit-ingestion/findings.md`.

### A legacy-looking audit topic constant exists but is not used as a sink

- `control-plane-api/src/services/kafka_service.py` also defines `Topics.AUDIT_EVENTS = "stoa.audit.events"`.
- Repo references to `stoa.audit.events` are documentation/runbook references and the constant itself.
- No Python consumer subscribes to `Topics.AUDIT_EVENTS`.

### PostgreSQL audit write path exists, but it is not the Kafka sink

- `control-plane-api/src/services/audit_service.py` writes to the `audit_events` table via `AuditService.record_event(...)`.
- `control-plane-api/src/opensearch/audit_middleware.py` dual-writes mutating HTTP requests to PostgreSQL when `AuditMiddleware` has an audit logger.
- Chat and some governance paths write directly through `AuditService.record_event(...)`.
- None of these paths consumes `stoa.audit.trail` or `audit-log`.

### Kafka consumer patterns exist for other topics

Existing consumer examples:

- `control-plane-api/src/consumers/deployment_consumer.py`
  - topic `stoa.deployment.events`
  - group `deployment-notification-consumer`
- `control-plane-api/src/consumers/promotion_deploy_consumer.py`
  - topic `stoa.deploy.requests`
  - group `promotion-deploy-consumer`
- `control-plane-api/src/workers/chat_metering_consumer.py`
  - topic `stoa.chat.tokens_used`
  - group `chat-metering-consumer`
- `control-plane-api/src/workers/billing_metering_consumer.py`
  - topic `stoa.metering`
  - group `billing-metering-consumer`
- `control-plane-api/src/workers/error_snapshot_consumer.py`
  - topic `stoa.errors.snapshots`
  - group `error-snapshot-consumer`

These provide implementation patterns only. None is an audit consumer.

### No audit consumer startup gate exists

`control-plane-api/src/main.py` starts several Kafka-backed consumers behind `STOA_ENABLE_KAFKA_CONSUMERS`, but there is no `ENABLE_AUDIT_CONSUMER`, no `audit_consumer_task`, and no import of an audit consumer singleton.

The test guard `control-plane-api/tests/test_regression_kafka_boot.py` lists the Kafka-backed startup flags and does not include an audit consumer.

### No deployment manifest restores an audit consumer

The relevant manifests and env files expose the control-plane API and Redpanda config, but no separate audit consumer workload or disabled audit consumer container was found:

- `control-plane-api/k8s/deployment.yaml`
- `deploy/config/prod.env`
- `deploy/config/staging.env`
- `deploy/config/dev.env`
- `charts/stoa-platform/templates/*`
- `.github/workflows/control-plane-api-ci.yml`

## Topic Contract Drift

The repo currently has at least three audit-topic names in circulation:

| Name | Evidence | Status |
|---|---|---|
| `stoa.audit.trail` | `Topics.AUDIT_LOG`, active `emit_audit_event(...)` producer | Active producer topic |
| `audit-log` | Prod Redpanda topic from PR-1A evidence | Runtime topic exists, no repo producer/consumer found |
| `stoa.audit.events` | `Topics.AUDIT_EVENTS` constant and runbooks | Documented/legacy, no repo consumer found |

This is a contract ambiguity. A restore PR should not guess which topic is authoritative.

## Decision

Do not implement a consumer in PR-1A2.

Reason: the goal permits restoration only if an implementation or deployment manifest already exists. The repository only provides generic patterns and producer-side code. Building a new Kafka-to-PostgreSQL audit consumer would be new ingestion architecture, not a restore.

## Minimal Follow-Up Scope

A future implementation PR should be planned separately and should answer these questions before code:

1. Authoritative topic: choose `stoa.audit.trail`, `stoa.audit.events`, or a migration path between them.
2. Source of truth: decide whether compliance audit persistence is direct PostgreSQL writes, Kafka-to-PostgreSQL ingestion, or a shared audit abstraction that guarantees PostgreSQL persistence.
3. Consumer group: define the durable group name, for example `audit-events-consumer` or `audit-trail-consumer`.
4. Offset policy: decide whether first deployment starts at `earliest` for backfill or `latest` for forward-only restore.
5. Schema mapping: map Kafka envelope fields to `audit_events` required columns: `method`, `path`, `outcome`, `resource_type`, `actor_id`, `actor_email`, and `created_at`.
6. Idempotency: decide whether Kafka event id maps to `audit_events.id` or is stored in `details`, and how duplicate messages are handled.
7. Failure mode: keep user-facing API operations non-blocking, but make audit sink failures observable.
8. Deployment model: decide whether the consumer runs inside `stoa-control-plane-api` lifespan or as a separate worker Deployment.

## PR-1B Blocker

PR-1B must not start `/stats`, `/actions`, actor resolution, or UI refresh behavior while Kafka-only audit events are not persisted. Any UI/API aggregation would summarize incomplete audit data and could make the compliance surface look healthier than it is.

## Rollback

This PR is docs-only. Rollback is a simple `git revert` of the commit that adds this scoping document.
