# Sidecar and stoa-connect Observability Wiring

This records the narrow PR4 wiring for the Kubernetes sidecar and the Go
`stoa-connect` agent. It does not redesign the global pipeline.

## Component Matrix

| Component | Metrics | Traces | Logs | Notes |
| --- | --- | --- | --- | --- |
| Rust gateway sidecar mode | `*-stoa-sidecar` ServiceMonitor | `STOA_OTEL_ENDPOINT` -> Alloy OTLP | JSON gateway logs | Real same-pod sidecar. |
| Go stoa-connect | `/metrics` on the agent port | `OTEL_EXPORTER_OTLP_ENDPOINT` when set | JSON stdout logs | Separate from Rust connect-mode. |
| Rust connect-mode simulation | `stoa-gateway-connect-mode` Compose job | `STOA_OTEL_ENDPOINT` | JSON gateway logs | Compose-only simulation. |

## Kubernetes Sidecar

When `stoaSidecar.enabled=true`, the chart renders a third-party gateway plus
the Rust `stoa-sidecar` container. PR4 adds a dedicated `*-stoa-sidecar` service
and ServiceMonitor for `/metrics` on port `8081`.

The ServiceMonitor adds only bounded operational labels: `cluster`,
`environment`, and `deployment_mode=sidecar`. It does not add `tenant_id`,
`consumer_id`, `trace_id`, `span_id`, request IDs, raw paths, or payload-derived
values as Prometheus labels.

The sidecar receives `STOA_OTEL_ENDPOINT` from `stoaSidecar.otelEndpoint`, which
defaults to Alloy.

## Go stoa-connect

The Go agent exposes `/metrics` on `STOA_CONNECT_PORT` (default `8090`). Metrics
stay agent-level and do not carry trace IDs, span IDs, request IDs, or consumer
IDs as labels.

`stoa-connect` logs JSON with `service.name`, `service.version`,
`service.instance.id`, `environment`, `tenant_id`, `trace_id`, and `span_id`.
The webhook endpoint is wrapped with OTel HTTP instrumentation so request logs
can include active span context when tracing is configured or propagated.
