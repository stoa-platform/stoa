# Gateway Metrics Cardinality

This document records the PR 2 producer-side gateway metric changes that follow
`docs/observability/telemetry-contract.md`.

## Scope

PR 2 reduces Prometheus cardinality at the Rust gateway producer boundary.

It does not:

- redesign Console Observability;
- rewire OTel, Loki, Tempo, OpenSearch, Fluent Bit, Data Prepper, or Alloy;
- change sidecar or stoa-connect telemetry wiring;
- rationalize OpenSearch usage;
- change tenant authorization behavior;
- change sampling policy.

## Changes

| Metric | Previous labels | PR 2 labels | Contract status | Notes |
| --- | --- | --- | --- | --- |
| `stoa_http_requests_total` | `method`, `path`, `status` | `method`, `http_route`, `status` | improved | `http_route` contains a normalized route label, never raw request path. |
| `stoa_http_request_duration_seconds` | `method`, `path` | `method`, `http_route` | improved | Same normalized route projection as the request counter. |
| `stoa_mcp_tools_calls_total` | `tool`, `tenant`, `status`, `consumer_id` | `tool`, `tenant`, `status` | improved | `consumer_id` removed from Prometheus labels. |
| `stoa_quota_remaining` | `consumer`, `period` | not emitted | removed | Per-consumer quota values must be exposed through tenant-safe APIs, traces, or logs, not Prometheus labels. |

## Remaining Gateway Labels

| Label | Current use | Status | Follow-up |
| --- | --- | --- | --- |
| `http_route` | HTTP request count and latency | canonical | Keep normalized. |
| `method` | HTTP, API proxy, sender-constraint metrics | allowed | Keep bounded. |
| `status` | HTTP status code and bounded MCP/API outcomes | legacy bounded | Consider `status_code` or `status_class` in a compatibility PR. |
| `tenant` | MCP, SSE/WS, rate-limit, token budget, discovery, and security metrics | legacy limited | PR 1B readers support `tenant` and `tenant_id`; producer rename requires a compatibility PR. |
| `tool` | MCP tool metrics, guardrails injection, fallback metrics | legacy limited | PR 1B readers normalize `tool` to `tool_name`; broad tool metrics still need an allowlist decision. |
| `route_id` | WS/SOAP/gRPC/GraphQL proxy route metrics | limited | Allowed only when route IDs are bounded control-plane identifiers. |
| `upstream` | pool, upstream latency, circuit breaker, load balancer metrics | limited | Use only for bounded upstream IDs or normalized names. |
| `api` | demo-facing dynamic proxy metric | limited | Must remain a stable API identifier, not raw path or URL. |
| `consumer_id` / `consumer` | removed from gateway Prometheus metrics touched by PR 2 | forbidden | Use traces/logs or tenant-safe product APIs. |

## Compatibility Notes

PR 2 does not rename the MCP `tenant` and `tool` labels because PR 1B already
added reader-side compatibility for legacy and canonical projections. Migrating
those producer labels to `tenant_id` and `tool_name` should be a separate
compatibility PR with reader and dashboard coverage.

Console pages that still query direct PromQL by `path` are tracked as Console
Observability productization work. Gateway HTTP producers now emit `http_route`
for the canonical label projection.

## Phase 6.0 Guardrails Full Metrics Contract

References:

- Master ticket: CAB-2213
- Phase ticket: CAB-2214
- Plan: `docs/plans/2026-05-11-guardrails-non-mcp-4b-full.md`
- Decision log: `docs/decisions/2026-05-11-guardrails-non-mcp-4b-full.md`
- Source plan: `docs/plans/2026-05-09-observability-data-visibility.md`
- Source decision log: `docs/decisions/2026-05-09-observability-data-visibility.md`

Phase 6.0 prepares the additive full guardrails metric contract. It does not
implement producers, readers, dashboards, enforcement, or smoke jobs.

### Proposed Metrics

| Metric | Labels | Max series | Notes |
| --- | --- | ---: | --- |
| `stoa_guardrails_evaluations_total` | `deployment_mode`, `surface`, `guardrail` | 100 | One increment per execution of one guardrail policy against one request context. Disabled and skipped/not-applicable policies do not increment. |
| `stoa_guardrails_decisions_total` | `deployment_mode`, `surface`, `guardrail`, `decision` | 400 | One decision increment for started evaluations only. |

Maximum budget:

```text
deployment_mode: 5 values
surface:         4 values
guardrail:       5 values
decision:        4 values

evaluations_total = 5 * 4 * 5     = 100 series
decisions_total   = 5 * 4 * 5 * 4 = 400 series
combined ceiling  = 500 series
```

Reviewer authority: any reviewer may reject a Phase 6 implementation if a new
guardrails metric exceeds the 500-series ceiling, uses a label outside this
section, or introduces any forbidden label listed below.

### Locked Label Enums

`deployment_mode` values:

- `edge-mcp`
- `sidecar`
- `proxy`
- `shadow`
- `unknown`

`surface` values:

- `mcp`
- `api_proxy`
- `dynamic_proxy`
- `ws_proxy`

`guardrail` values:

- `pii`
- `injection`
- `prompt_guard`
- `content_filter`
- `rate_limit`

`decision` values:

- `allow`
- `redact`
- `block`
- `error`

Forbidden `decision` values:

- `not_applicable`
- `bypass`
- `flag`
- `rate_limited`

`rate_limit` decisions must use `guardrail="rate_limit"` and
`decision="block"` when enforcement blocks a request/message.

### Forbidden Labels

The new guardrails metrics must never expose:

- `tenant_id`
- `tenant`
- raw route values
- raw policy names or policy IDs
- `tool`
- `trace_id`
- `span_id`
- `request_id`
- `user_id`
- `consumer`
- raw path values
- raw URL values
- payload-derived labels

Route information is intentionally omitted from Phase 6 guardrails counters.
If a future plan reintroduces route attribution, it must use normalized route
templates only, never raw request paths, query strings, IDs, or user input.

### Producer Presence

Phase 6 uses zero-initialized bounded series as the default producer-presence
mechanism. A freshly-started gateway with no guardrail-applicable traffic must
still expose the bounded zero-valued series needed for the Control Plane API to
distinguish `no_evaluations` from `metrics_unavailable`.

A separate producer-present gauge is allowed only through a challenger-approved
amendment.

Phase 6.1 implements option (a) in `stoa-gateway/src/metrics.rs`: the gateway
registers both full guardrails counters at metrics initialization and
pre-creates zero-valued series for the A10 in-scope producer matrix
(`edge-mcp/mcp`, `proxy/api_proxy`, `proxy/dynamic_proxy`, `proxy/ws_proxy`)
across all five guardrail values and the four locked decision values. The
startup presence set is 20 evaluation series plus 80 decision series, inside
the documented 500-series ceiling.

### Surface Coverage Matrix

| Deployment mode | Surface | File anchor | Phase 6 scope |
| --- | --- | --- | --- |
| `edge-mcp` | `mcp` | `stoa-gateway/src/lib.rs:139`, `stoa-gateway/src/mcp/handlers.rs:680` | In scope. MCP tool calls are the primary producer path. |
| `proxy` | `api_proxy` | `stoa-gateway/src/lib.rs:214`, `stoa-gateway/src/proxy/api_proxy_handler.rs:120`, `stoa-gateway/src/proxy/api_proxy_handler.rs:327`, `stoa-gateway/src/proxy/api_proxy_handler.rs:342`, `stoa-gateway/src/proxy/observe_only_guardrails.rs:111` | In scope, observe-only first. JSON body evaluation emits bounded full guardrail counters without request/response mutation. |
| `proxy` | `dynamic_proxy` | `stoa-gateway/src/proxy/dynamic.rs:148`, `stoa-gateway/src/proxy/dynamic.rs:356`, `stoa-gateway/src/proxy/dynamic.rs:358`, `stoa-gateway/src/proxy/dynamic.rs:366`, `stoa-gateway/src/proxy/observe_only_guardrails.rs:55` | In scope, observe-only first. Bounded JSON bodies are restored before forwarding; non-JSON, oversized, streaming, and invalid JSON bodies are skipped without counter increments. |
| `proxy` | `ws_proxy` | `stoa-gateway/src/ws/proxy.rs:12`, `stoa-gateway/src/ws/proxy.rs:41`, `stoa-gateway/src/ws/proxy.rs:165`, `stoa-gateway/src/ws/proxy.rs:201` | Deferred. Follow-up required before `ws_proxy` emits full guardrail counters because payload bounding, no per-frame evaluation, and no behavior-change proof are not locked for long-lived streams. |
| `sidecar` | any | n/a | Deferred. Needs its own surface proof before producer work. |
| `shadow` | any | `stoa-gateway/src/router/shadow.rs:21` | Deferred. Shadow parity/capture paths are not Phase 6 guardrail producers. |

Excluded from guardrail producer coverage:

- Kubernetes and process health/readiness/liveness routes:
  `stoa-gateway/src/lib.rs:100`, `stoa-gateway/src/lib.rs:101`,
  `stoa-gateway/src/lib.rs:102`, `stoa-gateway/src/lib.rs:103`.
- Prometheus scrape route: `stoa-gateway/src/lib.rs:104`.
- Admin health and admin/internal operator routes:
  `stoa-gateway/src/handlers/admin/router.rs:54`,
  `stoa-gateway/src/handlers/admin/router.rs:56`,
  `stoa-gateway/src/handlers/admin/health.rs:31`.

### API Semantic Fields

The Control Plane API owns the semantic state. The UI must render this state and
must not derive it from raw counts or timestamps.

Required top-level and per-guardrail fields:

- `state`
- `evaluations_count`
- `decisions_count`
- `trips_count`
- `error_count`
- `last_evaluation_delta_at`
- `last_decision_delta_at`
- `scrape_sample_at`
- `source_healthy`
- `stale_reason`
- `by_guardrail`

Allowed `state` values:

- `metrics_unavailable`
- `no_evaluations`
- `evaluations_zero_trips`
- `trips_observed`
- `stale_data`

Allowed `stale_reason` values:

- `prom_unreachable`
- `scrape_gap`
- `producer_absent`
- `stale_unknown`

`stale_reason` must never contain raw Prometheus errors, hostnames, internal
URLs, raw query strings, request IDs, or trace IDs.

Count formulas:

- `trips_count = decisions_total{decision="redact"} + decisions_total{decision="block"}`
- `error_count = decisions_total{decision="error"}`

One stale guardrail does not make the top-level state stale while other
guardrails are healthy. If all guardrails are stale, the top-level state may be
`stale_data`.
