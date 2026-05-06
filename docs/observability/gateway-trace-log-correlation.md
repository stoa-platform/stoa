# Gateway Trace/Log Correlation

This document records the narrow PR3 implementation of the observability
contract for gateway access logs. It does not rewire telemetry pipelines.

## Scope

Gateway structured access logs MUST expose the correlation fields needed to
navigate between live traces and logs:

| Log field | Source | Fallback | Notes |
| --- | --- | --- | --- |
| `trace_id` | Current OTel span context captured by `http_metrics_middleware` | `x-stoa-trace-id`, then `-` | Allows log-to-trace correlation in Loki/Tempo. |
| `span_id` | Current OTel span context captured by `http_metrics_middleware` | `-` | Represents the local gateway span, not an incoming parent span. |
| `tenant_id` | Gateway request extensions | empty string | Present when auth/tenant context is known. |
| `consumer_id` | Gateway request extensions | empty string | Logs only; still forbidden as a Prometheus label. |
| `service.name` | Static gateway service identity | none | `stoa-gateway`. |
| `service.version` | Cargo package version | none | Matches the gateway build version. |

## Non-goals

This change does not:

- add trace or span IDs to Prometheus labels;
- change Prometheus metrics or cardinality;
- redesign Console Observability;
- rewire Loki, Tempo, OpenSearch, Fluent Bit, Data Prepper, or Alloy;
- change tenant authorization or server-side tenant filtering;
- change OTel sampling behavior.
