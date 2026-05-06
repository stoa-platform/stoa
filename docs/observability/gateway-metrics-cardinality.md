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
