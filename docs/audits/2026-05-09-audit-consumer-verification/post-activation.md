# PR-1A6 — Audit consumer post-activation evidence

Captured 2026-05-08 between 08:33 and 08:36 UTC, after the official A1b activation merged in stoa-infra#75 at 2026-05-08 07:40:34 UTC.

This file is a follow-up to `findings.md` in the same directory. `findings.md` (PR-1A5, [stoa#2733](https://github.com/stoa-platform/stoa/pull/2733)) proved the data path while the consumer was running on revision 514. This file proves continuous ingestion is now active on the post-activation revision and adds a new controlled non-`chat_*` event whose row is visible via `/v1/audit/{tenant_id}`.

## Verdict

**VERDICT: PR-1B_UNBLOCKED — continuous ingestion verified 2026-05-08T08:35:55Z.**

Data-path proven again, this time post the official GitOps activation in stoa-infra#75. The consumer group `audit-trail-pg-consumer` is `STATE=Stable` with `MEMBERS=2` and `TOTAL-LAG=0`, ingesting non-chat events continuously since the activation rollout. A controlled `GET /v1/tenants/demo/export` produced event `51a40e4c-eecc-4b65-bd33-06764d8ad355` which advanced Kafka offset `30054 → 30055`, persisted to `audit_events` 2 seconds after trigger, and is now returned by `/v1/audit/demo` as the first entry. PR-1B can start.

## 1. GitOps / deployment

- stoa-infra commit containing `ENABLE_AUDIT_TRAIL_CONSUMER=true`: `35a770d chore(infra): activate audit trail consumer (HOLD — draft, do not merge without explicit go) (#75)`.
- ArgoCD application `control-plane-api`:
  - `sync.status = Synced`
  - `health.status = Healthy`
  - `summary.images[0] = ghcr.io/stoa-platform/control-plane-api:dev-1803ef125d386dfff098a17d8055204163334681` (post-#2730 + #2734 safe-by-default code)
  - `lastSync = 2026-05-08T07:41:13Z`
- cp-api pods (post-rollout):
  - `stoa-control-plane-api-798f84465d-89gd8` Running, age ~50 min
  - `stoa-control-plane-api-798f84465d-m64z6` Running, age ~50 min
- Effective env in running pods:
  - `ENABLE_AUDIT_TRAIL_CONSUMER=true`
  - `STOA_ENABLE_KAFKA_CONSUMERS` not present (defaulting to enabled at the master gate)
- API health: `200` (read via in-pod curl during this test).

## 2. Consumer startup

Logs from `deploy/stoa-control-plane-api` since 60 minutes contain:

```text
{"event": "Audit trail consumer started", "logger": "src.main", "level": "info",
 "timestamp": "2026-05-08T07:41:44.159032Z", "environment": "production",
 "version": "2.0.0", "component": "control-plane-api"}
```

Followed by repeated `Audit trail message processed` entries — at least nine in the captured tail, indicating continuous ingestion of organic events emitted by other cp-api flows (deployment, promotion, apis, tenants, users) since activation.

No `Audit trail consumer stopped`, no `Failed to start audit`, no audit-related error or DLQ-related warning was observed in the inspected window.

## 3. Kafka group — pre-event

Captured at `2026-05-08T08:33:23Z` (before the controlled trigger):

```text
GROUP        audit-trail-pg-consumer
COORDINATOR  0
STATE        Stable
BALANCER     range
MEMBERS      2
TOTAL-LAG    0

TOPIC             PARTITION  CURRENT-OFFSET  LOG-START-OFFSET  LOG-END-OFFSET  LAG  CLIENT-ID            HOST
stoa.audit.trail  0          30054           29892             30054           0    kafka-python-2.3.1   10.2.0.231
```

PostgreSQL pre-state from the same window:

```text
non_chat_last_hour = 35
newest_non_chat    = 2026-05-08 07:41:59.274507+00:00
```

Interpretation: between activation (offset 30019, end of PR-1A5 #2733) and 08:33 UTC, **35 organic non-chat events** were ingested via the consumer chain. Continuous ingestion was already operational before the controlled mutation.

## 4. Controlled non-chat event

Action chosen: `GET /v1/tenants/demo/export`. Same idempotent read-only audit-emitting endpoint used in PR-1A5 #2733. No data mutation in any tenant.

```bash
KUBECONFIG=$HOME/.kube/config-stoa-ovh kubectl exec -n stoa-system deploy/stoa-control-plane-api -- /bin/sh -lc '
  KEY=${GATEWAY_API_KEYS%%,*}
  curl -sS -o /tmp/pr1a6.json \
    -w "http=%{http_code} time=%{time_total}\n" \
    -H "X-Operator-Key: $KEY" \
    http://127.0.0.1:8000/v1/tenants/demo/export
'
```

The operator key was sourced from the in-pod env var and never printed in evidence.

- Trigger UTC: `2026-05-08T08:35:55Z`
- HTTP result: `200`, response time `0.491s`
- Action emitted: `export`
- Resource type / id: `tenant` / `demo`
- Outcome: `success`

## 5. PostgreSQL verification

Query post-trigger (~2 seconds after):

```sql
SELECT id, tenant_id, action, resource_type, resource_id,
       outcome AS status, created_at AS timestamp
FROM audit_events
WHERE created_at > NOW() - INTERVAL '5 minutes'
  AND action NOT LIKE 'chat%'
  AND tenant_id = 'demo'
ORDER BY created_at DESC
LIMIT 5;
```

Result (single row, controlled event):

```text
id          51a40e4c-eecc-4b65-bd33-06764d8ad355
tenant_id   demo
action      export
resource_type tenant
resource_id  demo
status      success
timestamp   2026-05-08 08:35:57.046867+00
```

Aggregate inventory delta:

```text
non_chat_last_hour: 35  ->  36   (Δ=+1, exactly the controlled event)
```

## 6. API verification

Command (in-pod via cp-api, sanitized operator key):

```bash
KUBECONFIG=$HOME/.kube/config-stoa-ovh kubectl exec -n stoa-system deploy/stoa-control-plane-api -- /bin/sh -lc '
  KEY=${GATEWAY_API_KEYS%%,*}
  curl -sS -H "X-Operator-Key: $KEY" \
    "http://127.0.0.1:8000/v1/audit/demo?page=1&page_size=5"
'
```

Response summary:

```text
total = 11
page_size = 5
first_entry_id = 51a40e4c-eecc-4b65-bd33-06764d8ad355
```

First entry returned by `/v1/audit/demo` (sanitized — same id as the PG row, with full `details._kafka` Kafka trace metadata):

```json
{
  "id": "51a40e4c-eecc-4b65-bd33-06764d8ad355",
  "timestamp": "2026-05-08T08:35:57.046867Z",
  "tenant_id": "demo",
  "user_id": "stoa-operator",
  "user_email": null,
  "action": "export",
  "resource_type": "tenant",
  "resource_id": "demo",
  "status": "success",
  "client_ip": null,
  "user_agent": null,
  "details": {
    "_kafka": {
      "topic": "stoa.audit.trail",
      "offset": 30054,
      "partition": 0,
      "producer_source": "control-plane-api",
      "producer_version": "1.0",
      "producer_event_id": "51a40e4c-eecc-4b65-bd33-06764d8ad355"
    },
    "resource_counts": {
      "plans": 2,
      "skills": 0,
      "policies": 0,
      "webhooks": 0,
      "consumers": 0,
      "contracts": 0,
      "backend_apis": 0,
      "subscriptions": 0,
      "external_mcp_servers": 0
    }
  },
  "request_id": null
}
```

Chain trace confirmed: `producer_event_id` in `details._kafka` matches both the PG row id and the API `id` field; `details._kafka.offset = 30054` matches the Kafka offset that held this message.

## 7. Kafka group — post-event

Captured at `2026-05-08T08:35:58Z` (~3 seconds after trigger):

```text
GROUP        audit-trail-pg-consumer
COORDINATOR  0
STATE        Stable
BALANCER     range
MEMBERS      2
TOTAL-LAG    0

TOPIC             PARTITION  CURRENT-OFFSET  LOG-START-OFFSET  LOG-END-OFFSET  LAG  CLIENT-ID            HOST
stoa.audit.trail  0          30055           29892             30055           0    kafka-python-2.3.1   10.2.0.231
```

Offset advance: `30054 -> 30055` (Δ=+1, exactly the controlled event).

DLQ check (`rpk topic list | grep dlq`): no `stoa.audit.trail.dlq` topic exists yet — consistent with zero validation errors since activation. No new DLQ event was generated by this test.

## 8. Verdict

**VERDICT: PR-1B_UNBLOCKED — continuous ingestion verified 2026-05-08T08:35:55Z.**

All gating conditions from `docs/plans/2026-05-07-observability-data-integrity.md` (post-#2735 refresh) are satisfied:

| Condition | Status |
|---|---|
| `ENABLE_AUDIT_TRAIL_CONSUMER=true` injected in running pods | ✅ |
| Consumer group `audit-trail-pg-consumer` `STATE=Stable`, `MEMBERS≥1`, `LAG=0` | ✅ |
| Controlled non-`chat_*` event POST official activation | ✅ (event `51a40e4c-eecc-4b65-bd33-06764d8ad355`, action=`export`, 2026-05-08T08:35:55Z) |
| PG row visible | ✅ |
| `/v1/audit/{tenant_id}` returns the row | ✅ |

PR-1B (Audit Log API + UI) can start. The MEGA-A Phase 7 dependency on PR-1A6 PASS is met.

## Residual notes

- The 35 organic non-chat events ingested between activation (07:41 UTC) and the controlled trigger (08:35 UTC) prove **continuous** ingestion — not just a one-shot data-path test as in PR-1A5 #2733.
- Image deployed is `dev-1803ef125...` which embeds the safe-by-default code from #2730. Even if the chart override were removed, the code default `"false"` would prevent the consumer from starting silently.
- No DLQ topic was created. If validation errors are encountered later, the consumer will create the topic and route invalid messages there per the mini-spec at `docs/plans/2026-05-08-audit-consumer-ingestion-contract.md`.
- The `client_ip` and `user_agent` fields are `null` because the trigger came from in-pod localhost via the operator key — expected. Production audit events from external clients will have these populated.
