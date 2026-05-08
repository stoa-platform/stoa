# PR-1A5 Audit Consumer Runtime Verification

Evidence captured: 2026-05-07 19:20-19:28 UTC. The directory date follows the requested artifact path (`2026-05-09`), but the runtime verification happened on 2026-05-07.

## Verdict

**Data-path result: PASS.** While the audit trail consumer was running on deployment revision 514, a non-`chat_*` audit event was produced to `stoa.audit.trail`, consumed by `audit-trail-pg-consumer`, persisted to PostgreSQL `audit_events`, and returned by `/v1/audit/demo`.

**Current live-state caveat: consumer disabled after the test.** During evidence collection, `stoa-control-plane-api` rolled from revision 514 to revision 515. The current live Deployment still runs image `ghcr.io/stoa-platform/control-plane-api:dev-6400f51a51b32e4f3fb9d2b8010a90dc9d2ae8cc`, but now has `ENABLE_AUDIT_TRAIL_CONSUMER=false`; after the rollout, the Kafka group is `Empty` with zero members. Treat this as proof that #2726 can persist the event when enabled, not proof that the consumer is currently enabled for continuous prod ingestion.

## 1. Deployment state

Commands used:

```bash
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh kubectl config current-context
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh kubectl get deploy stoa-control-plane-api -n stoa-system -o json
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh kubectl get pods -n stoa-system -l app=stoa-control-plane-api -o wide
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh kubectl logs -n stoa-system deploy/stoa-control-plane-api --since=45m --all-containers=true
```

- Environment: OVH prod (`kubectl` context `ovh-prod`).
- Namespace: `stoa-system`.
- Deployed commit SHA: `6400f51a51b32e4f3fb9d2b8010a90dc9d2ae8cc` from image tag `dev-6400f51a51b32e4f3fb9d2b8010a90dc9d2ae8cc`.
- Implementation PR: #2726 (`feat(api,infra): audit consumer implementation`), merged 2026-05-07 18:39 UTC.
- Deployment status after final rollout: revision `515`, `replicas=2`, `readyReplicas=2`, `availableReplicas=2`, `updatedReplicas=2`; rollout status succeeded.
- Current pods after final rollout:
  - `stoa-control-plane-api-7b478fc4d8-q5n47`: `1/1 Running`, IP `10.2.0.225`.
  - `stoa-control-plane-api-7b478fc4d8-tt2j2`: `1/1 Running`, IP `10.2.0.226`.
- Consumer deployment model: no separate Deployment; the consumer runs in-process inside `stoa-control-plane-api`.
- `ENABLE_AUDIT_TRAIL_CONSUMER` during the successful test window: env var was unset on revision 514, and #2726 defaulted the flag to `true`; startup logs included `Audit trail consumer started`.
- Current `ENABLE_AUDIT_TRAIL_CONSUMER` after revision 515 rollout: explicit value `false`.
- Current `STOA_ENABLE_KAFKA_CONSUMERS`: unset, defaulting to enabled at the master gate, but the audit-specific flag now disables this consumer.

Relevant startup log from the successful window:

```text
2026-05-07T18:50:36.969316Z Audit trail consumer started
Audit trail consumer started
```

## 2. Kafka consumer state

Commands used:

```bash
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh kubectl exec -n stoa-system redpanda-0 -- rpk topic list
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh kubectl exec -n stoa-system redpanda-0 -- rpk group describe audit-trail-pg-consumer
```

Topic inventory:

```text
NAME              PARTITIONS  REPLICAS
stoa.audit.trail  1           1
```

Before the test event, while revision 514 was active:

```text
GROUP        audit-trail-pg-consumer
STATE        Stable
MEMBERS      2
TOTAL-LAG    0

TOPIC             PARTITION  CURRENT-OFFSET  LOG-START-OFFSET  LOG-END-OFFSET  LAG
stoa.audit.trail  0          30018           29892             30018           0
```

After the test event was consumed:

```text
GROUP        audit-trail-pg-consumer
STATE        Stable
MEMBERS      2
TOTAL-LAG    0

TOPIC             PARTITION  CURRENT-OFFSET  LOG-START-OFFSET  LOG-END-OFFSET  LAG
stoa.audit.trail  0          30019           29892             30019           0
```

Current state after revision 515 disabled the consumer:

```text
GROUP        audit-trail-pg-consumer
STATE        Empty
MEMBERS      0
TOTAL-LAG    0

TOPIC             PARTITION  CURRENT-OFFSET  LOG-START-OFFSET  LOG-END-OFFSET  LAG
stoa.audit.trail  0          30019           29892             30019           0
```

Summary:

- Topic: `stoa.audit.trail`.
- Consumer group: `audit-trail-pg-consumer`.
- Group exists: yes.
- Assigned partitions during the successful test: partition `0` assigned to a `kafka-python-2.3.1` member on pod IP `10.2.0.213`.
- Current assigned partitions: none, because the group is now empty.
- Current lag: `0`.
- Last committed offset available: `30019`.

## 3. Test event produced

Action performed:

```bash
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh kubectl exec -n stoa-system deploy/stoa-control-plane-api -- /bin/sh -lc '
KEY=${GATEWAY_API_KEYS%%,*}
curl -sS -o /tmp/pr1a5-tenant-export.json -w "%{http_code}" \
  -H "X-Operator-Key: $KEY" \
  http://127.0.0.1:8000/v1/tenants/demo/export
'
```

The operator key was sourced inside the pod and was not printed.

- Action performed: `GET /v1/tenants/demo/export`.
- Tenant id: `demo`.
- Approximate trigger timestamp: `2026-05-07T19:24:38.202017+00:00`.
- HTTP result: `200`.
- Expected audit action: `export`.
- Expected resource type: `tenant`.
- Expected resource id: `demo`.
- Sanitized response evidence: `resource_counts={"backend_apis":0,"consumers":0,"contracts":0,"external_mcp_servers":0,"plans":2,"policies":0,"skills":0,"subscriptions":0,"webhooks":0}`.

Producer log:

```text
Published audit event to stoa.audit.trail: b9ca45fb-67b3-4823-98af-c198c3d68871
```

## 4. PostgreSQL verification

Pre-state query result:

```sql
SELECT count(*) AS non_chat_last_hour_count,
       max(created_at) AS newest_non_chat_created_at
FROM audit_events
WHERE created_at > NOW() - INTERVAL '1 hour'
  AND action NOT LIKE 'chat%';
```

```text
non_chat_last_hour_count | newest_non_chat_created_at
-------------------------+----------------------------
0                        |
```

Equivalent verification query. The model uses `created_at` and `outcome`, so the query aliases them to the prompt's `timestamp` and `status` names:

```sql
SELECT id,
       tenant_id,
       action,
       resource_type,
       resource_id,
       outcome AS status,
       created_at AS timestamp
FROM audit_events
WHERE created_at > NOW() - INTERVAL '1 hour'
  AND action NOT LIKE 'chat%'
ORDER BY created_at DESC
LIMIT 20;
```

Result:

```text
id                                   | tenant_id | action | resource_type | resource_id | status  | timestamp
-------------------------------------+-----------+--------+---------------+-------------+---------+-------------------------------
b9ca45fb-67b3-4823-98af-c198c3d68871 | demo      | export | tenant        | demo        | success | 2026-05-07 19:24:38.666762+00
```

## 5. API verification

Command used:

```bash
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh kubectl exec -n stoa-system deploy/stoa-control-plane-api -- /bin/sh -lc '
KEY=${GATEWAY_API_KEYS%%,*}
curl --max-time 10 -fsS \
  -H "X-Operator-Key: $KEY" \
  "http://127.0.0.1:8000/v1/audit/demo?page=1&page_size=20"
'
```

Result summary:

```text
total=10
page=1
page_size=20
```

Matching entry returned by `/v1/audit/demo`:

```json
{
  "action": "export",
  "client_ip": null,
  "details": {
    "_kafka": {
      "offset": 30018,
      "partition": 0,
      "producer_event_id": "b9ca45fb-67b3-4823-98af-c198c3d68871",
      "producer_source": "control-plane-api",
      "producer_version": "1.0",
      "topic": "stoa.audit.trail"
    },
    "resource_counts": {
      "backend_apis": 0,
      "consumers": 0,
      "contracts": 0,
      "external_mcp_servers": 0,
      "plans": 2,
      "policies": 0,
      "skills": 0,
      "subscriptions": 0,
      "webhooks": 0
    }
  },
  "id": "b9ca45fb-67b3-4823-98af-c198c3d68871",
  "request_id": null,
  "resource_id": "demo",
  "resource_type": "tenant",
  "status": "success",
  "tenant_id": "demo",
  "timestamp": "2026-05-07T19:24:38.666762Z",
  "user_agent": null,
  "user_email": null,
  "user_id": "stoa-operator"
}
```

## 6. Follow-up

The #2726 ingestion path is proven by event `b9ca45fb-67b3-4823-98af-c198c3d68871`. Current production runtime is not continuously consuming because revision 515 explicitly sets `ENABLE_AUDIT_TRAIL_CONSUMER=false`. Re-enable the flag only through the intended deployment path, then rerun the Kafka group check to confirm `STATE=Stable` and `MEMBERS>0`.
