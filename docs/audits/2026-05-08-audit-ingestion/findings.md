# PR-1A — Audit Ingestion Investigation

Generated: 2026-05-07T15:19:15+02:00

Scope: read-only OVH prod investigation. No source code or runtime state was modified.

## Verdict

**BLOCKED_FOR_PR-1B_SCOPING**

Production has a PostgreSQL `audit_events` table, and the Control Plane API can publish audit events to Kafka, but no live audit consumer was found in OVH prod. Redpanda has audit topics, yet no consumer group is subscribed to either `stoa.audit.trail` or `audit-log`. The PostgreSQL audit table is also stale: newest row is `2026-05-03 20:04:46+00`, with `0` rows in the last 24 hours at investigation time.

PR-1B should not assume a small UI/API cleanup. It must first choose the runtime contract:

- keep audit source of truth as direct API middleware writes to PostgreSQL;
- or introduce/restore an explicit Kafka audit consumer that persists audit topics into PostgreSQL.

## Read-Only Commands

All Kubernetes commands used the explicit prod kubeconfig:

```bash
KUBECONFIG=$HOME/.kube/config-stoa-ovh kubectl ...
```

Confirmed context:

```text
current-context: ovh-prod
namespace inspected: stoa-system
cluster control plane: https://rhq5qw.c1.gra9.k8s.ovh.net
```

No `kubectl apply`, `patch`, `delete`, `rollout`, `scale`, migration, Kafka write, or SQL write was executed.

## 1. Runtime Inventory

Kubernetes workloads in `stoa-system` relevant to audit ingestion:

| Workload | Kind | Ready | Image / role |
|---|---:|---:|---|
| `stoa-control-plane-api` | Deployment | 2/2 | `ghcr.io/stoa-platform/control-plane-api:dev-14e39073a4ba9a88321b19a2a8138db1a15cf713` |
| `control-plane-db` | StatefulSet | 1/1 | `postgres:15-alpine` |
| `redpanda` | StatefulSet | 1/1 | `docker.redpanda.com/redpandadata/redpanda:v24.3.1` |
| `redpanda-console` | Deployment | 1/1 | `docker.redpanda.com/redpandadata/console:v2.8.11` |

No deployment, statefulset, job, or pod with an audit-consumer role was present in `stoa-system`.

Relevant API env inventory, with secrets redacted:

```text
KAFKA_BOOTSTRAP_SERVERS=redpanda.stoa-system.svc.cluster.local:9092
DATABASE_URL=<set>
PROMETHEUS_INTERNAL_URL=http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090
```

Gateway Kafka env:

```text
STOA_KAFKA_ENABLED=true
STOA_KAFKA_BROKERS=redpanda.stoa-system.svc.cluster.local:9092
STOA_KAFKA_METERING_TOPIC=stoa.metering
STOA_KAFKA_ERRORS_TOPIC=stoa.errors
```

## 2. Kafka Topic + Consumer State

Redpanda topic inventory:

```text
audit-log
deploy-requests
gateway-sync-requests
stoa.api.lifecycle
stoa.audit.trail
stoa.chat.tokens_used
stoa.deploy.requests
stoa.deployment.events
stoa.deployment.logs
stoa.deployment.progress
stoa.errors
stoa.errors.snapshots
stoa.gateway.events
stoa.gateway.sync.requests
stoa.metering
stoa.tenant.lifecycle
stoa.tenant.provisioning
tenant-events
```

Audit topics exist:

| Topic | Partitions | Replicas | Retention |
|---|---:|---:|---:|
| `audit-log` | 1 | 1 | `604800000` ms |
| `stoa.audit.trail` | 1 | 1 | `604800000` ms |

Consumer groups:

```text
billing-metering-consumer         Empty
chat-metering-consumer            Stable
deployment-notification-consumer  Stable
error-snapshot-consumer           Stable
git-sync-worker                   Stable
promotion-deploy-consumer         Stable
sync-engine                       Stable
```

Consumer group topic mapping:

| Group | Topic | State | Lag |
|---|---|---|---:|
| `billing-metering-consumer` | `stoa.metering` | Empty | 70959 |
| `chat-metering-consumer` | `stoa.chat.tokens_used` | Stable | 0 |
| `deployment-notification-consumer` | `stoa.deployment.events` | Stable | 0 |
| `error-snapshot-consumer` | `stoa.errors.snapshots` | Stable | 0 |
| `git-sync-worker` | `stoa.api.lifecycle` | Stable | 0 |
| `promotion-deploy-consumer` | `stoa.deploy.requests` | Stable | 0 |
| `sync-engine` | `stoa.gateway.sync.requests` | Stable | 0 |

Finding: no listed consumer group is subscribed to `stoa.audit.trail` or `audit-log`.

## 3. PostgreSQL `audit_events` Inventory

Tables with audit naming:

```text
public.audit_events
public.workflow_audit_logs
```

`audit_events` schema columns:

```text
id, tenant_id, actor_id, actor_email, actor_type, action, method, path,
resource_type, resource_id, resource_name, outcome, status_code, client_ip,
user_agent, correlation_id, details, diff, duration_ms, created_at
```

No row-level PII values were exported. Only aggregate counts were queried.

Aggregate inventory:

| Metric | Value |
|---|---:|
| Total rows | 113562 |
| Oldest row | `2026-03-12 13:31:43.731145+00` |
| Newest row | `2026-05-03 20:04:46.718213+00` |
| Rows last 24h | 0 |
| Rows last 7d | 53 |
| Total relation size | 65 MB |
| Table size | 34 MB |

Outcome distribution:

| Outcome | Count |
|---|---:|
| `success` | 90515 |
| `failure` | 23047 |

Top actions:

| Action | Count |
|---|---:|
| `data.modified` | 113427 |
| `chat_conversation_create` | 87 |
| `chat_tool_call` | 26 |
| `subscription.created` | 12 |
| `tenant.updated` | 3 |
| `tenant.created` | 3 |
| `user.created` | 2 |
| `authentication` | 2 |

Top resource types:

| Resource type | Count |
|---|---:|
| `unknown` | 113429 |
| `chat_conversation` | 87 |
| `chat_tool` | 26 |
| `subscription` | 12 |
| `tenant` | 6 |
| `user` | 2 |

Tenant distribution:

| Tenant | Count | Newest row |
|---|---:|---|
| `unknown` | 113449 | `2026-04-09 19:01:56.213543+00` |
| `high-five` | 53 | `2026-05-03 20:04:46.718213+00` |
| `free-aech` | 42 | `2026-04-04 14:24:22.704068+00` |
| `acme-corp` | 15 | `2026-04-20 14:34:58.726742+00` |
| `free-torpedo` | 2 | `2026-03-16 21:26:24.149175+00` |
| `free-i-r0k` | 1 | `2026-03-19 21:32:10.570838+00` |

Recent daily counts in the last 14 days:

| Day | Count |
|---|---:|
| `2026-05-03` | 4 |
| `2026-05-02` | 26 |
| `2026-05-01` | 23 |

Finding: `audit_events` is not receiving current prod audit flow, or current prod user activity did not hit any PG-writing audit path after `2026-05-03`. Given the Kafka consumer gap and ongoing traffic elsewhere, treat this as an ingestion architecture gap until proven otherwise.

## 4. Source Emit Site Inventory

Read-only source scan:

```bash
rg -n "record_event\(|AuditService\(|emit_audit_event" control-plane-api/src -S
```

Observed emit/write patterns:

| Area | Evidence | Sink pattern | Status |
|---|---|---|---|
| `control-plane-api/src/opensearch/audit_middleware.py` | imports `AuditService`, calls `record_event(...)` | Direct PostgreSQL write | UNKNOWN runtime coverage |
| `control-plane-api/src/services/chat_service.py` | calls `AuditService.record_event(...)` | Direct PostgreSQL write | CONFIRMED historical rows (`chat_*`) |
| `control-plane-api/src/routers/chat.py` | calls `AuditService.record_event(...)` | Direct PostgreSQL write | CONFIRMED historical rows (`chat_*`) |
| `control-plane-api/src/services/identity_governance.py` | calls `AuditService.record_event(...)` | Direct PostgreSQL write | UNKNOWN runtime coverage |
| `control-plane-api/src/routers/audit.py` | self-audit export / erasure paths call `record_event(...)` | Direct PostgreSQL write | UNKNOWN runtime coverage |
| `control-plane-api/src/services/deployment_service.py` | calls `kafka_service.emit_audit_event(...)` | Kafka `stoa.audit.trail` | CONFIRMED_UNCONSUMED |
| `control-plane-api/src/services/promotion_service.py` | calls `kafka_service.emit_audit_event(...)` | Kafka `stoa.audit.trail` | CONFIRMED_UNCONSUMED |
| `control-plane-api/src/routers/apis.py` | calls `kafka_service.emit_audit_event(...)` | Kafka `stoa.audit.trail` | CONFIRMED_UNCONSUMED |
| `control-plane-api/src/routers/tenants.py` | calls `kafka_service.emit_audit_event(...)` | Kafka `stoa.audit.trail` | CONFIRMED_UNCONSUMED |
| `control-plane-api/src/routers/users.py` | calls `kafka_service.emit_audit_event(...)` | Kafka `stoa.audit.trail` | CONFIRMED_UNCONSUMED |

Supporting code facts:

- `Topics.AUDIT_LOG = "stoa.audit.trail"` in `control-plane-api/src/services/kafka_service.py`.
- `emit_audit_event(...)` publishes event type `"audit"` to `Topics.AUDIT_LOG`.
- `create_consumer(...)` exists generically, but no prod consumer group for audit topics was found.
- `control-plane-api/src/routers/audit.py` documents PostgreSQL `audit_events` as source of truth, then OpenSearch fallback, then demo fallback.

## 5. Logs

Command:

```bash
kubectl logs -n stoa-system deploy/stoa-control-plane-api --since=6h --tail=2000 |
  rg -i 'audit|stoa\.audit|audit-log|consumer|kafka'
```

Observed output:

```text
Found 2 pods, using pod/stoa-control-plane-api-97b4cd5c7-v4j8f
```

No matching log lines were found in that pod tail for the inspected window.

## 6. Hypotheses

| Hypothesis | Result | Evidence |
|---|---|---|
| H1: Kafka consumer `audit-events -> audit_events PG` is down or not deployed | Supported | audit topics exist, but no audit consumer group or audit workload found |
| H2: non-chat paths swallow Kafka audit errors | Not proven | source scan shows Kafka emitters; no matching log evidence in last 6h |
| H3: audit topic exists only in some envs | Refuted for prod topic existence | `stoa.audit.trail` and `audit-log` exist in prod Redpanda |
| H4: multiple sinks exist | Supported | direct PG writes via `AuditService`, Kafka audit emits via `kafka_service.emit_audit_event` |
| H5: tenant filter excludes most events | Not primary | PG contains many rows under tenant `unknown`; staleness affects all tenants after May 3 |

## Recommended PR-1B Scope

Minimum safe PR-1B scope should include:

1. Decide and document the audit source-of-truth contract:
   - direct PostgreSQL append-only writes from API middleware/service paths;
   - or Kafka audit topics persisted by an explicit consumer.
2. If keeping Kafka audit emitters, add or restore an audit consumer deployment and consumer group for `stoa.audit.trail`.
3. If moving to direct PG writes, replace Kafka-only `emit_audit_event(...)` sites for compliance-critical operations with `AuditService.record_event(...)` or a shared audit abstraction that guarantees PG persistence.
4. Keep audit failures non-blocking for user operations, but log structured warnings with action, resource type, and sink.
5. Add `/v1/audit/{tenant_id}/stats` and `/actions` only after the ingestion contract is clear; otherwise UI stats will summarize incomplete data.
6. Disable silent demo fallback in prod, as already decided in AR-3.

## Residual Risks

- This was a read-only point-in-time inspection; no manual API create was triggered, so current middleware coverage was not end-to-end proven.
- The `unknown` tenant/resource population indicates historic schema or middleware attribution issues that may require a separate data-quality remediation.
- `billing-metering-consumer` has high lag on `stoa.metering`; it is adjacent, not audit-specific, but it signals broader consumer supervision risk.
