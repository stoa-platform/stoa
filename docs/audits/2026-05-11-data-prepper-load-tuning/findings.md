# Phase 0.5c - Data Prepper Load Tuning

- Date: 2026-05-11
- Scope: Observability Data Visibility follow-up 0.5c
- Kube context: `ovh-prod` via `KUBECONFIG=/Users/torpedo/.kube/config-stoa-ovh`
- Mode: read-only diagnostic plus one idempotent gateway probe
- Verdict: `monitor_only`

## References

- Plan: `docs/plans/2026-05-09-observability-data-visibility.md`
- Decision log: `docs/decisions/2026-05-09-observability-data-visibility.md`
- Handoff: `/Users/torpedo/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/handoff_session_2026_05_10_observability_data_visibility_closed.md`

## Summary

Phase 0.5c does not require an infra tuning patch right now.

The handoff trigger for this follow-up was the post-0.5a observation that Data Prepper briefly showed roughly 10 minutes of indexing lag, `bulkRequestLatency_max=11.89s`, and some Alloy `DeadlineExceeded` errors after the Data Prepper listener fix. The 2026-05-11 re-check shows the backlog cleared and no persistent Data Prepper/Alloy error pattern.

The pipeline is live from gateway traces into OpenSearch. A fresh idempotent probe generated gateway trace `453484aa194a174879dff61c6f99f8a8` at `2026-05-11T11:09:21Z`; OpenSearch returned all 5 expected `stoa-gateway` spans for that trace at `2026-05-11T11:10:32Z`, so the observed indexing delay was at most 71 seconds for this probe.

## Trigger Criteria

0.5c should move from `monitor_only` to `tuning_required` only if at least one condition is true:

- OpenSearch trace indexing lag exceeds 30 minutes.
- Data Prepper or Alloy Data Prepper export errors persist after the post-deploy catch-up window.
- Data Prepper buffer remains non-zero and does not drain under normal traffic.
- Bulk request retries, timeout errors, failed requests, or server errors increase during steady state.

None of these conditions was true during this check.

## Evidence

### Component State

`opensearch/stoa-data-prepper` was healthy:

```text
deployment.apps/stoa-data-prepper 1/1 available
pod/stoa-data-prepper-844f5f46c5-sn9gt 1/1 Running, restarts=0, age=19h
service/stoa-data-prepper ports: 21890/TCP, 4900/TCP
endpoints/stoa-data-prepper: 10.2.0.142:21890, 10.2.0.142:4900
resources: requests 100m CPU / 256Mi memory, limits 500m CPU / 512Mi memory
kubectl top: 26m CPU, 344Mi memory
```

The deployed Data Prepper config still matches the 0.5a fix:

```yaml
source:
  otel_trace_source:
    port: 21890
    ssl: false
    health_check_service: true
buffer:
  bounded_blocking:
    buffer_size: 4096
    batch_size: 256
sink:
  - opensearch:
      hosts:
        - "https://opensearch-cluster-master.opensearch.svc.cluster.local:9200"
      index_type: trace-analytics-raw
      bulk_size: 5
```

### Error Persistence Check

No matching Data Prepper or Alloy Data Prepper export error lines were found in the recent steady-state windows:

```text
SINCE=12h dataprepper_error_lines=0 alloy_dataprepper_error_lines=0
SINCE=6h  dataprepper_error_lines=0 alloy_dataprepper_error_lines=0
SINCE=2h  dataprepper_error_lines=0 alloy_dataprepper_error_lines=0
SINCE=30m dataprepper_error_lines=0 alloy_dataprepper_error_lines=0
```

The 24h log window still contains the short post-0.5a catch-up burst around `2026-05-10T15:52Z` to `15:54Z`:

- Data Prepper `Buffer does not have enough capacity left` timeouts.
- gRPC `ClosedStreamException: received a RST_STREAM frame: CANCEL`.
- Alloy `DeadlineExceeded` retries to `otelcol.exporter.otlp.dataprepper`.

Those errors did not persist into the 12h/6h/2h/30m windows.

### Buffer And Throughput

Data Prepper metrics were sampled over 60 seconds:

```text
SNAPSHOT_1 2026-05-11T11:07:56Z
recordsInBuffer=206
recordsWriteFailed_total=24888
documentsSuccessFirstAttempt_total=2081098
bulkRequestNumberOfRetries_total=0
bulkRequestServerErrors_total=0
recordsRead_total=2082142
requestsReceived_total=30683

SNAPSHOT_2 2026-05-11T11:08:56Z
recordsInBuffer=0
recordsWriteFailed_total=24888
documentsSuccessFirstAttempt_total=2083155
bulkRequestNumberOfRetries_total=0
bulkRequestServerErrors_total=0
recordsRead_total=2083803
requestsReceived_total=30707
```

Delta over the sample:

- Buffer drained from 206 to 0 records.
- Successful first-attempt OpenSearch documents increased by 2,057.
- `recordsWriteFailed_total` stayed flat.
- OpenSearch bulk retry and server error counters stayed flat at 0.

Later metric spot-check:

```text
bulkRequestLatency_seconds_max=1.088574484
bulkRequestLatency_seconds_count=1143
bulkRequestLatency_seconds_sum=1359.546107326
bulkRequestFailed_total=0
bulkRequestErrors_total=0
bulkRequestTimeoutErrors_total=0
bulkRequestNumberOfRetries_total=0
bulkRequestServerErrors_total=0
recordsInBuffer=159
```

The non-zero buffer value in the later spot-check was transient. The earlier one-minute sample showed the buffer can drain to zero under current traffic.

### OpenSearch Recency

OpenSearch trace indices are receiving data:

```text
otel-v1-apm-span-000018 1656855 docs 709mb
```

The latest span query at the time of collection returned a recent `stoa-gateway` span:

```json
{
  "traceId": "8cbb294a93e803ddba1368d3a1185e0d",
  "name": "proxy.dynamic",
  "startTime": "2026-05-11T11:07:18.371331301Z",
  "serviceName": "stoa-gateway"
}
```

### Fresh Probe

Probe request:

```text
PROBE_ID=phase05c-20260511T110921Z-379
INJECTED_TRACE_ID=83f6e737b412ab9c0945a0c7999b39cf
START_UTC=2026-05-11T11:09:21Z
GET https://mcp.gostoa.dev/apis/echo-fallback/
HTTP_STATUS=404
```

The `404` is acceptable for this diagnostic because it is the same route-resolution miss pattern used in Phase 0: it is idempotent and creates only synthetic telemetry.

The injected trace id `83f6e737b412ab9c0945a0c7999b39cf` was not adopted by the gateway. The gateway generated and logged trace id `453484aa194a174879dff61c6f99f8a8`; the 0.5c conclusion follows that gateway trace because this follow-up measures Data Prepper/OpenSearch indexing lag, not inbound `traceparent` propagation. Inbound trace propagation remains a separate gateway behavior to investigate if the product requires it.

Gateway log:

```json
{
  "timestamp": "2026-05-11T11:09:21.948957Z",
  "method": "GET",
  "path": "/apis/echo-fallback/",
  "status": 404,
  "user_agent": "stoa-phase05c-probe/2026-05-11",
  "trace_id": "453484aa194a174879dff61c6f99f8a8",
  "span_id": "4a524a82fe0076c2"
}
```

OpenSearch lookup at `2026-05-11T11:10:32Z` returned 5 spans for trace `453484aa194a174879dff61c6f99f8a8`:

```text
http.request       2026-05-11T11:09:21.947745603Z
policy.supervision 2026-05-11T11:09:21.948396608Z
policy.quota       2026-05-11T11:09:21.948479784Z
auth.profile       2026-05-11T11:09:21.948516611Z
proxy.dynamic      2026-05-11T11:09:21.948588804Z
```

## Decision

Keep 0.5c as `monitor_only`. Do not change Data Prepper `buffer_size`, `batch_size`, `bulk_size`, CPU, or memory in this phase.

Reasons:

- The original post-0.5a lag/error burst no longer persists.
- A fresh gateway trace is visible in OpenSearch within the measured upper bound of 71 seconds.
- Data Prepper buffer drained to zero during the one-minute sample.
- OpenSearch bulk errors, retries, failed requests, timeout errors, and server errors are all zero.
- Data Prepper CPU and memory are not saturated.

## Reopen Conditions

Open a dedicated infra PR only if a later check shows:

- `max(now - latest OpenSearch span startTime) > 30 minutes` for `serviceName=stoa-gateway`; or
- `otel_traces_pipeline_BlockingBuffer_recordsInBuffer` remains non-zero for multiple consecutive samples and does not drain; or
- any OpenSearch sink counter increases: `bulkRequestFailed_total`, `bulkRequestErrors_total`, `bulkRequestTimeoutErrors_total`, `bulkRequestNumberOfRetries_total`, or `bulkRequestServerErrors_total`; or
- Alloy resumes persistent `otelcol.exporter.otlp.dataprepper` `DeadlineExceeded`, queue-full, dropped, or connection-refused errors.

Candidate tuning levers for that future PR:

1. Increase Data Prepper memory limit/request if JVM or buffer pressure appears.
2. Increase `buffer.bounded_blocking.buffer_size` only with memory headroom evidence.
3. Revisit `sink.opensearch.bulk_size` only after measuring OpenSearch bulk latency and rejection/timeout counters.
4. Add Prometheus alerting for indexing lag and Data Prepper sink errors before increasing ingestion volume.
