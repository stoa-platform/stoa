# Phase 0 — Probe Trace Walk

- Date: 2026-05-09
- Plan ref: `docs/plans/2026-05-09-observability-data-visibility.md`
- Phase: 0 — Gap 3 cluster diagnostic with traceable end-to-end probe
- Kube context: `ovh-prod` via `KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh`
- Verdict: `pipeline_partial`
- Code changes: none

## Summary

The trace pipeline is live through `stoa-gateway -> Alloy -> Tempo`, but it is not live through `Alloy -> Data Prepper -> OpenSearch`, and the Control Plane transaction list is not currently usable as the Live Calls trace source.

The strongest localized break is Data Prepper's OTLP trace ingest endpoint: the Kubernetes Service exposes `21890/TCP`, the pipeline config declares `otel_trace_source.port: 21890`, and NetworkPolicy allows Alloy to reach it, but the Data Prepper pod is not listening on `21890`. Alloy continuously fails with `connect: connection refused` and drops trace batches. A follow-up live read on 2026-05-10 showed Data Prepper's control API on `4900` was up while `21890` was absent from `/proc/net/tcp*`; startup logs showed the OpenSearch sink timing out before the OTLP source bound.

There is a second projection/config issue in the Control Plane API: `OPENSEARCH_HOST` points at `https://opensearch.opensearch.svc.cluster.local:9200`, which does not resolve in the cluster. The actual OpenSearch service observed during the probe is `opensearch-cluster-master.opensearch:9200`.

## Phase 0.5a Follow-Up

Phase 0.5a is hors plan `obs-data-visibility`; it unblocks Phase 5B full trace coverage.

Repo split decision:

- `stoa-infra`: owns the runtime fix in https://github.com/PotoMitan/stoa-infra/pull/77. The PR updates the Data Prepper Helm chart so startup waits for OpenSearch, keeps the Kubernetes service DNS instead of rewriting it to a startup-time IP, and gates readiness/liveness on the OTLP listener. It also updates cp-api Helm values to `https://opensearch-cluster-master.opensearch.svc.cluster.local:9200`.
- `stoa`: owns this documentation addendum only in https://github.com/stoa-platform/stoa/pull/2751. No application code changes are part of Phase 0.5a.

Namespace/service choice:

- Keep actual prod Alloy naming: `monitoring/alloy` with OTLP gRPC `4317` and HTTP `4318`.
- Do not rename infra to the older plan-side name `stoa-monitoring/stoa-alloy-otlp`.
- Treat `monitoring/alloy` as the canonical runtime name for follow-up probes and reviewer evidence.

## Probe IDs

The first route tried was `GET https://mcp.gostoa.dev/health`:

- Probe id: `probe-2026-05-09-0cab9c10`
- Injected W3C trace id: `ab50613e4c350ec57e8791168d959853`
- Result: `200 OK`
- Finding: not conclusive for gateway tracing because it did not appear in gateway access logs with the injected trace id.

The conclusive route was an idempotent gateway request:

- Route: `GET https://mcp.gostoa.dev/apis/echo-fallback/`
- Probe id: `probe-2026-05-09-732483b3`
- Injected W3C trace id: `2b57e0501d69440d27eeff2a6a27f846`
- HTTP result: `404 No matching API route`
- Gateway-extracted trace id: `6ff37f4f0c4dfc5f26e839aee7514461`

The `404` is acceptable for this diagnostic because the request is a read-only route resolution miss and did not mutate business data. It intentionally created synthetic telemetry only.

## Hop Results

| Hop | Result | Evidence |
|---|---:|---|
| Gateway pod OTel env | pass | `STOA_OTEL_ENDPOINT=http://alloy.monitoring:4317` in `deploy/stoa-gateway`. |
| Expected plan namespace/service | documented drift | Plan names `stoa-monitoring/stoa-alloy-otlp`; prod has no `stoa-monitoring` namespace. Actual service is `monitoring/alloy` with OTLP gRPC `4317` and HTTP `4318`. Phase 0.5a keeps the actual prod name and documents `monitoring/alloy` as canonical for follow-up probes. |
| Gateway access log | pass | Gateway logged `GET /apis/echo-fallback/`, `status=404`, `user_agent=stoa-phase0-probe/2026-05-09`, `trace_id=6ff37f4f0c4dfc5f26e839aee7514461`. |
| Injected `traceparent` adoption | fail/non-blocking | Injected trace id `2b57e0501d69440d27eeff2a6a27f846` was not used by the gateway; gateway generated `6ff37f4f0c4dfc5f26e839aee7514461`. The walk therefore follows the gateway-extracted trace id, which is allowed by A2. |
| Arbitrary header capture | not captured | `X-Probe-Id` was not observed as a span/log attribute. Verdict does not rely on this header. |
| Alloy service | pass | `monitoring/alloy` exists, DaemonSet `3/3`, service exposes `4317`, `4318`, endpoints present. |
| Gateway -> Alloy policy | pass | `monitoring/allow-stoa-to-alloy` allows `stoa-system` ingress to Alloy on `4317/TCP` and `4318/TCP`. |
| Alloy -> Tempo | pass | Direct Tempo fetch by gateway trace id returned spans for `http.request`, `policy.supervision`, `policy.quota`, `auth.profile`, and `proxy.dynamic`. |
| Tempo service | pass | `monitoring/stoa-tempo` is ready and `http://stoa-tempo.monitoring:3200/ready` returns `ready`. |
| Alloy -> Data Prepper | fail | Alloy logs repeatedly show `otelcol.exporter.otlp.dataprepper` connection refused to `10.3.171.87:21890`, queue full, and dropped trace batches. |
| Data Prepper deployment | partial | `opensearch/stoa-data-prepper` Deployment is `1/1` and control API `:4900/list` returns `otel-traces-pipeline`, but OTLP port `21890` refuses connections inside the pod. |
| Data Prepper metrics | fail | `otel_traces_pipeline_recordsProcessed_total=0`, `otel_traces_pipeline_opensearch_recordsIn_total=0`, buffer usage `0`. |
| Data Prepper -> OpenSearch | not reached by new spans | Data Prepper generated config targets `https://10.3.31.87:9200`; OpenSearch authentication works for diagnostic queries, but no new probe span reaches the sink because source ingest is closed. |
| OpenSearch trace index | partial | `otel-v1-apm-span-*` indices and legacy template exist, but searches for both the injected trace id and gateway trace id returned zero hits. |
| Control Plane `/v1/monitoring/transactions` list | fail | `GET /v1/monitoring/transactions?time_range=15&limit=5&route=/apis/echo-fallback/` returned `{"transactions":[],"total":0,"source":"none"}`. |
| Control Plane transaction detail | partial | `GET /v1/monitoring/transactions/6ff37f4f0c4dfc5f26e839aee7514461` returned the trace with `source="tempo"`. The injected trace id returned `source="none"` and no spans. |
| UI time-window implication | fail for list-driven UI | The UI list cannot show the probe through the transaction list API while it returns `source="none"` and `transactions=[]`, even though a known trace id can be fetched from Tempo. |

## Component Inventory

Present:

- `stoa-system/deployment/stoa-gateway` (`ghcr.io/stoa-platform/stoa-gateway:dev-b08e050368e1a2bed505bc5805a78a3740cc85f1`)
- `monitoring/daemonset/alloy` (`3/3`)
- `monitoring/service/alloy` (`4317`, `4318`)
- `monitoring/statefulset/stoa-tempo`
- `opensearch/deployment/stoa-data-prepper`
- `opensearch/service/stoa-data-prepper` (`21890`, `4900`)
- `opensearch/service/opensearch-cluster-master`
- OpenSearch legacy template `otel-v1-apm-span-index-template` for `otel-v1-apm-span-*`
- Existing OpenSearch trace indices `otel-v1-apm-span-*`

Missing or misconfigured:

- `stoa-monitoring/stoa-alloy-otlp` from the plan does not exist in prod; actual namespace/service are `monitoring/alloy`.
- Data Prepper OTLP listener on `21890` is not bound even though service, NetworkPolicy, and pipeline config say it should be.
- Control Plane API `OPENSEARCH_HOST` is configured to a non-existent DNS name: `opensearch.opensearch.svc.cluster.local`.
- Control Plane transaction list does not surface the Tempo trace, while transaction detail by known trace id does.
- Gateway does not adopt the inbound W3C `traceparent` trace id on the tested route.
- HTTP headers such as `X-Probe-Id` are not captured as trace attributes, so header search must not be used as proof of absence.

## Failure Modes Checked

| Failure mode | Status |
|---|---|
| Exporter OTel not initialized in gateway | Not supported by evidence: gateway emits trace ids and Tempo has gateway spans. |
| DNS / NetworkPolicy blocks gateway -> Alloy | Not supported by evidence: Alloy service, endpoints, and allow policy exist; Tempo receives spans. |
| Alloy receives but Data Prepper down/misconfigured | Confirmed: Alloy exporter to Data Prepper fails; Data Prepper OTLP listener refuses `21890`. |
| OpenSearch index absent or mapping rejects | Index absent is false; indices and template exist. Mapping rejection is not reached for new probe spans because Data Prepper ingest is closed. |
| Tempo fallback inactive | False: Tempo direct fetch and Control Plane transaction detail by known trace id return spans. |
| UI time range misses request window | Not the primary issue: list API returns no transactions/source `none` for a fresh 15-minute window, while detail by trace id returns from Tempo. |
| Headers not captured as OTel attributes | Confirmed: `X-Probe-Id` was not found; verdict avoids relying on it. |

## Verdict

`pipeline_partial`

The pipeline is not absent: gateway traces are generated and Tempo can store/retrieve them. It is not live end-to-end for the product surface: Data Prepper does not accept OTLP trace input on `21890`, OpenSearch does not receive the new probe span, and `/v1/monitoring/transactions` list returns no trace data for the UI.

## Phase 0.5b Post-Merge Verification

Date: 2026-05-10.

The original Phase 0 verdict above is retained as the historical diagnostic
state. After Phase 0.5a landed in stoa-infra, Phase 0.5b re-ran the gateway
trace walk and confirmed the drift was cleared for new gateway spans:

- ArgoCD reported `stoa-data-prepper`, `stoa-gateway`, and `control-plane-api`
  as `Synced` / `Healthy` at infra commit
  `44ef7ac3c141e0a9c6edd69b4aeb217e9af018f1`.
- `opensearch/stoa-data-prepper` pod
  `stoa-data-prepper-844f5f46c5-sn9gt` was `1/1 Running`.
- Data Prepper bound OTLP `21890` and health `4900`; `/proc/net/tcp6` showed
  listeners on `:5582` and `:1324`, with established Alloy connections on
  `21890`.
- `stoa-control-plane-api` had
  `OPENSEARCH_HOST=https://opensearch-cluster-master.opensearch.svc.cluster.local:9200`.

Probe:

- Probe id: `probe-2026-05-10-bae194b8`
- Route: `GET https://mcp.gostoa.dev/apis/echo-fallback/`
- HTTP result: `404 No matching API route`
- Injected W3C trace id: `b61e34fbb31ba2d1a18fe91f7399917f`
- Gateway-generated trace id: `884404306fbdaeb833d32b6741b7a0ac`

Post-fix hop matrix:

| Hop | Result | Evidence |
|---|---:|---|
| Gateway -> Alloy | pass | Gateway access log for `stoa-phase5b-probe/2026-05-10` recorded trace id `884404306fbdaeb833d32b6741b7a0ac` on `/apis/echo-fallback/`. |
| Alloy -> Data Prepper | pass | Data Prepper accepted new OTLP traffic on `21890`; Alloy logs after the probe no longer showed Data Prepper exporter `DeadlineExceeded`, `refused`, queue-full, or dropped-data errors. |
| Data Prepper -> OpenSearch | pass | OpenSearch `_search?q=traceId:884404306fbdaeb833d32b6741b7a0ac` returned 5 hits in `otel-v1-apm-span-000017`. |
| Control Plane transaction detail | pass | `/v1/monitoring/transactions/884404306fbdaeb833d32b6741b7a0ac` returned HTTP `200`, `source="opensearch"`, `span_count=5`. |
| Control Plane transaction list | pass | `/v1/monitoring/transactions?time_range=15&limit=5&route=/apis/echo-fallback/` returned HTTP `200`, `source="opensearch"`, `total=5`. |
| Tempo fallback | pass | `stoa-tempo.monitoring:3200/ready` returned `ready`, and `/api/traces/884404306fbdaeb833d32b6741b7a0ac` returned 5 spans. |

Phase 5B uses this post-merge state for trace-hop applicability. The automated
probe and operator runbook live in `docs/observability/gateway-telemetry-probe.md`.

## Recommended Next Work

1. Done in Phase 0.5a/0.5b: make `opensearch/stoa-data-prepper` actually listen on OTLP `21890` by starting it only after OpenSearch is reachable and by failing readiness/liveness when `21890` is not bound.
2. Done in Phase 0.5a/0.5b: update Control Plane `OPENSEARCH_HOST` to the real service (`opensearch-cluster-master.opensearch.svc.cluster.local:9200`) rather than creating an alias for the stale `opensearch.opensearch` name.
3. Done in Phase 0.5b: transaction list now returns `source="opensearch"` for fresh gateway spans once the trace index receives Data Prepper output.
4. Gateway tracing fix candidate: decide whether inbound `traceparent` must be honored; if yes, add a follow-up outside Phase 0.
