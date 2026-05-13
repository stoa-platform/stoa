# Gateway Telemetry Probe

- Plan ref: `docs/plans/2026-05-09-observability-data-visibility.md`
- Phase: 5B - gateway runtime telemetry probe
- Decision ref: `docs/decisions/2026-05-09-observability-data-visibility.md`
- Phase 0 trace walk: `docs/audits/2026-05-09-observability-data-visibility/probe-trace-walk.md`

This probe is manual only. It must never run automatically in production; use
`OPERATOR_OPT_IN=operator-approved` for any production execution.

## Scope

Phase 5B proves the runtime gateway path:

1. `gateway request -> Prometheus scrape`
2. `/v1/metrics/query_range -> UI Live Calls data source`
3. If Phase 0 verdict is not `pipeline_absent`: `gateway request -> OTel -> Alloy -> Data Prepper -> OpenSearch -> /v1/monitoring/transactions`

Phase 5A audit traffic is separate and remains covered by
`control-plane-api/scripts/probes/audit_pipeline_probe.py`.

## Probe

Script:

```bash
stoa-gateway/probes/runtime_telemetry_probe.py --help
```

Production shape:

```bash
# If running from a laptop, first port-forward OpenSearch or use an
# operator-approved reachable endpoint.
# kubectl -n opensearch port-forward svc/opensearch-cluster-master 9200:9200
# Optional direct Prometheus hop:
# kubectl -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090

OPERATOR_OPT_IN=operator-approved \
STOA_OPERATOR_KEY="<operator key from Vault/Kubernetes>" \
OPENSEARCH_URL="https://127.0.0.1:9200" \
OPENSEARCH_USER="<vault-backed user>" \
OPENSEARCH_PASSWORD="<vault-backed password>" \
STOA_GATEWAY_LOG_LOOKUP=1 \
KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh \
stoa-gateway/probes/runtime_telemetry_probe.py \
  --environment production \
  --phase0-verdict pipeline_partial \
  --prometheus-url http://127.0.0.1:9090
```

The script emits one JSON document with binary hop statuses. Required hops fail
closed unless Phase 0 is `pipeline_absent`, in which case trace hops are marked
`blocked_by_infra`.

## Hop Matrix

| Hop | Required when | Pass condition |
|---|---|---|
| `gateway_request` | always | Idempotent gateway request returns an accepted status, default `200,204,404`. |
| `prometheus_direct` | when `PROMETHEUS_URL` is set | Direct Prometheus instant query has a positive value for `stoa_http_requests_total`. |
| `metrics_query_range` | always | `/v1/metrics/query_range` returns a non-empty positive matrix for the route query. |
| `gateway_trace_id` | trace validation | `--gateway-trace-id` is supplied or gateway logs expose the generated trace id. |
| `opensearch_span` | Phase 0 verdict != `pipeline_absent` | `otel-v1-apm-span-*` contains spans for the gateway trace id. |
| `monitoring_transaction` | Phase 0 verdict != `pipeline_absent` | `/v1/monitoring/transactions/<trace_id>` returns spans with `source="opensearch"`. |

## Phase 0.5b Evidence

Run date: 2026-05-10.

0.5a infra was reconciled before this probe:

- ArgoCD `stoa-data-prepper`, `stoa-gateway`, and `control-plane-api` were `Synced` / `Healthy` at infra commit `44ef7ac3c141e0a9c6edd69b4aeb217e9af018f1`.
- `opensearch/stoa-data-prepper` pod `stoa-data-prepper-844f5f46c5-sn9gt` was `1/1 Running`.
- Data Prepper `/proc/net/tcp6` showed listeners on `:5582` (`21890`) and `:1324` (`4900`), plus established Alloy connections on `21890`.
- `stoa-control-plane-api` env exposed `OPENSEARCH_HOST=https://opensearch-cluster-master.opensearch.svc.cluster.local:9200`.

Probe request:

- Probe id: `probe-2026-05-10-bae194b8`
- Route: `GET https://mcp.gostoa.dev/apis/echo-fallback/`
- HTTP result: `404 No matching API route`
- Injected W3C trace id: `b61e34fbb31ba2d1a18fe91f7399917f`
- Gateway-generated trace id: `884404306fbdaeb833d32b6741b7a0ac`

Trace evidence:

- Gateway access log contains `user_agent=stoa-phase5b-probe/2026-05-10`, path `/apis/echo-fallback/`, status `404`, trace id `884404306fbdaeb833d32b6741b7a0ac`.
- OpenSearch `_search?q=traceId:884404306fbdaeb833d32b6741b7a0ac` returned 5 hits in `otel-v1-apm-span-000017`: `proxy.dynamic`, `auth.profile`, `policy.quota`, `policy.supervision`, `http.request`.
- `/v1/monitoring/transactions/884404306fbdaeb833d32b6741b7a0ac` returned HTTP `200`, `source="opensearch"`, `span_count=5`.
- `/v1/monitoring/transactions?time_range=15&limit=5&route=/apis/echo-fallback/` returned HTTP `200`, `source="opensearch"`, `total=5`.
- Tempo fallback remained live: `http://stoa-tempo.monitoring:3200/ready` returned `ready`, and `/api/traces/884404306fbdaeb833d32b6741b7a0ac` returned 5 spans.

Metrics evidence:

- Direct Prometheus instant query for `sum by (http_route) (increase(stoa_http_requests_total{http_route="/apis/echo-fallback/"}[5m]))` returned a positive vector for `/apis/echo-fallback/`.
- Direct Prometheus `query_range` returned a non-empty matrix for the same route and window.
- Pre-fix `/v1/metrics/query_range` returned an empty matrix because cp-api formatted aware datetimes as `2026-05-10T15:55:23+00:00Z`, which Prometheus rejects. This PR fixes cp-api to send epoch timestamps.

## Notes

The gateway does not currently adopt the inbound W3C `traceparent` trace id on
the tested route. Phase 5B therefore follows the gateway-generated trace id from
the access log, matching the Phase 0 trace walk behavior.
