# STOA Observability Constitution

## 1. Purpose

This document defines the observability contract between STOA services,
telemetry pipelines, storage backends, APIs, and Console UI.

It is the source of truth for:

- canonical telemetry fields
- backend-specific projections
- Prometheus metric and label policy
- tenant-safety requirements
- telemetry sensitivity and retention expectations
- metric compatibility and deprecation rules
- product-facing observability views

This PR does not fix the current observability implementation. It defines what
"correct" means before any producer, pipeline, backend, API, or Console behavior
is changed.

## 2. Non-goals

This contract does not:

- refactor the Console UI
- change production telemetry pipelines
- remove OpenSearch, Loki, Tempo, Prometheus, Fluent Bit, or Data Prepper
- rename emitted metrics or labels without compatibility
- change OpenTelemetry sampling behavior
- modify tenant authorization logic
- define exact retention durations for every environment
- replace existing runbooks

## 3. Normative Language

The keywords MUST, SHOULD, MAY, and FORBIDDEN are normative:

- MUST: required for new or migrated observability code
- SHOULD: preferred unless there is a documented reason
- MAY: optional and situational
- FORBIDDEN: not allowed in new telemetry and must be removed from migrated
  telemetry through the compatibility process

## 4. Backend Roles

STOA uses multiple observability backends, but each backend has a bounded role.

| Backend | Primary role | Product role | Notes |
| --- | --- | --- | --- |
| Prometheus | Metrics, alerting, SLOs | Gateway Health, platform health | Not a high-cardinality analytics backend. |
| Tempo | Live traces | Live Calls and call flow | Primary backend for request/span timelines. |
| Loki | Structured logs | Trace/log correlation | Logs MUST include correlation fields where available. |
| OpenSearch | Audit, security, search, forensics | Security & Guardrails | Not the primary live observability path. |
| Grafana | Expert/operator debugging | Expert mode only | SHOULD NOT be the default product Console. |
| Console API | Tenant-safe access layer | Product observability API | MUST enforce authorization server-side. |

## 5. Canonical Telemetry Model

STOA defines canonical concepts first, then projects them into OpenTelemetry,
Prometheus, JSON logs, OpenSearch, and Console API responses.

OpenTelemetry standard semantic conventions SHOULD be used when a standard
field exists. STOA-specific product fields MUST use the `stoa.*` namespace in
OpenTelemetry attributes.

| Concept | Canonical STOA field | OTel projection | Prometheus projection | Logs JSON projection | Console API projection | Sensitivity | Cardinality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Tenant | `tenant_id` | `stoa.tenant_id` | allowlisted only | `tenant_id` | `tenant_id` | customer identifier | medium/high |
| Gateway | `gateway_id` | `stoa.gateway_id` | allowlisted | `gateway_id` | `gateway_id` | internal/customer infra | medium |
| Deployment mode | `deployment_mode` | `stoa.deployment_mode` | allowlisted | `deployment_mode` | `deployment_mode` | low | low |
| Service name | `service.name` | `service.name` | `service` or job label | `service.name` | `service_name` | low | low |
| Service version | `service.version` | `service.version` | build/info metrics only | `service.version` | `service_version` | low | low |
| Service instance | `service.instance.id` | `service.instance.id` | limited | `service.instance.id` | operator/debug only | low/medium | medium/high |
| Trace ID | `trace_id` | span context | never label | `trace_id` | `trace_id` | debug/security-sensitive | unbounded |
| Span ID | `span_id` | span context | never label | `span_id` | `span_id` | debug/security-sensitive | unbounded |
| Request ID | `request_id` | `stoa.request_id` | forbidden | `request_id` | debug only | debug identifier | unbounded |
| HTTP route | `http.route` | `http.route` | `http_route` only if normalized | `http.route` | `http_route` | low/medium | bounded if normalized |
| Raw path | forbidden | forbidden | forbidden | debug-redacted only if needed | forbidden | may contain sensitive data | unbounded |
| HTTP method | `http.method` | `http.request.method` | `method` | `method` | `method` | low | low |
| Status code | `http.status_code` | `http.response.status_code` | `status_code` or `status_class` | `status_code` | `status_code` | low | bounded |
| Status class | `status_class` | `stoa.status_class` | `status_class` preferred | `status_class` | `status_class` | low | low |
| Tool name | `tool_name` | `stoa.tool_name` | limited allowlist only | `tool_name` | `tool_name` | medium | potentially high |
| Consumer ID | `consumer_id` | `stoa.consumer_id` | forbidden | `consumer_id` | restricted/admin only | customer/user identifier | high |
| Upstream | `upstream_id` | `stoa.upstream_id` | limited allowlist only | `upstream_id` | `upstream_id` | internal/customer infra | medium/high |
| Error type | `error_type` | `error.type` or `stoa.error_type` | allowlisted if bounded | `error_type` | `error_type` | medium | bounded if controlled |
| Guardrail decision | `guardrail_decision` | `stoa.guardrail.decision` | allowlisted aggregate only | `guardrail_decision` | `guardrail_decision` | high | low |
| Policy ID | `policy_id` | `stoa.policy_id` | limited allowlist only | `policy_id` | `policy_id` | security-sensitive | medium |

## 6. Prometheus Metric Policy

Prometheus is not a high-cardinality analytics backend.

A field MAY be used as a Prometheus label only if:

1. it is explicitly listed in the label allowlist;
2. its cardinality is bounded or operationally justified;
3. it does not contain raw user input, request IDs, trace IDs, paths, payload
   data, or customer secrets;
4. it is required for alerting, SLOs, product health, or operational debugging;
5. it has an owner and documented removal process.

Metric names SHOULD:

- use the `stoa_` prefix for STOA-owned metrics;
- use base units such as seconds and bytes;
- use `_total` only for counters;
- use `_seconds`, `_bytes`, or another unit suffix where applicable;
- represent one logical measurement across all label dimensions.

Metric names MUST NOT:

- mix units in one metric;
- encode label names into the metric name when labels are the right model;
- use `_total` on gauges;
- expose payload-derived values as labels.

### 6.1 Forbidden Prometheus Labels

The following labels are FORBIDDEN on Prometheus metrics:

- `trace_id`
- `span_id`
- `request_id`
- raw `path`
- raw URL
- `consumer_id`
- user IDs
- session IDs
- arbitrary tool names unless explicitly allowlisted
- payload-derived values
- email addresses
- tokens, API keys, secrets, or credential fragments

### 6.2 Prometheus Label Allowlist

| Label | Status | Allowed on | Forbidden on | Notes |
| --- | --- | --- | --- | --- |
| `service` | allowed | all service-level metrics | none | Low cardinality. |
| `gateway_id` | limited | gateway health/SLO metrics | runtime/process metrics unless needed | Medium cardinality. |
| `deployment_mode` | allowed | gateway/platform metrics | none | Examples: `edge-mcp`, `sidecar`, `proxy`, `shadow`. |
| `tenant_id` | limited | client-facing SLO metrics only | internal/runtime metrics | MUST be tenant-safe and server-side filtered. |
| `http_route` | limited | HTTP request metrics | raw path metrics | MUST be normalized. |
| `method` | allowed | HTTP metrics | none | Bounded. |
| `status_class` | preferred | HTTP metrics | none | Prefer over exact code where possible. |
| `status_code` | allowed | HTTP metrics | none | Bounded, but status class is cheaper. |
| `tool_name` | limited | explicitly approved tool metrics | broad gateway metrics | Can grow quickly. |
| `policy_id` | limited | security/guardrail aggregates | broad gateway metrics | Requires owner approval. |
| `upstream_id` | limited | upstream health metrics | broad request metrics | Use only if bounded. |
| `consumer_id` | forbidden | none | all metrics | Traces/logs only. |

### 6.3 Client-Facing Metric Rule

`tenant_id` MAY be used only on metrics that are explicitly client-facing or SLO
critical, such as tenant-scoped gateway availability, latency, and tool success
rate. It MUST NOT be added to process, runtime, exporter, queue internals, or
unbounded diagnostic metrics.

When a metric needs rich dimensions such as consumer, request, raw path, payload
shape, arbitrary tool name, or trace identifiers, that data MUST go to traces
and logs instead of Prometheus labels.

## 7. Recommended STOA SLIs

Product dashboards and alerts SHOULD be derived from named SLIs, not from an
inventory of whatever metrics happen to exist.

| SLI | Primary backend | Required dimensions | Notes |
| --- | --- | --- | --- |
| Gateway request availability | Prometheus | `service`, `deployment_mode`, optional `tenant_id` | Non-5xx over total requests. |
| Gateway p95/p99 latency | Prometheus | `service`, `deployment_mode`, optional `tenant_id` | Uses normalized route only when needed. |
| Tool call success rate | Prometheus + Tempo | optional `tenant_id`, limited `tool_name` | Tool label requires allowlist. |
| Policy/guardrail decision latency | Prometheus + OpenSearch | `deployment_mode`, optional `tenant_id` | Security-sensitive. |
| Sidecar sync freshness | Prometheus | `gateway_id`, optional `tenant_id` | Measures last successful sync age. |
| stoa-connect heartbeat freshness | Prometheus | `gateway_id`, service instance if needed | Measures agent reachability. |
| Control Plane API availability | Prometheus | `service`, `http_route` | Internal/operator SLO. |
| Trace/log correlation success | Smoke test | `service` | Operational validation, not necessarily a Prom metric. |

## 8. Metric and Label Compatibility Policy

Metric and label renames MUST follow a compatibility window.

For any rename:

1. document the old name and new name;
2. update readers to support old and new;
3. add a recording rule or alias where appropriate;
4. migrate dashboards and API queries;
5. add tests proving queried metrics exist;
6. mark the old name deprecated;
7. remove the old name only after an explicit removal PR.

No Console API endpoint, dashboard, alert, or SLO may depend on a metric that is
not emitted, aliased, or covered by a compatibility rule.

### 8.1 Initial Legacy Inventory

This table records known compatibility issues from the current codebase audit.
It is not yet the full migration plan.

| Legacy metric or label | Replacement | Compatibility strategy | Owner | Removal target |
| --- | --- | --- | --- | --- |
| `tenant` label | `tenant_id` | Readers support old + new; producers migrate through explicit PR. | platform/gateway | TBD |
| `tenant.id` / `resource.attributes.tenant@id` | `stoa.tenant_id` / API `tenant_id` | Map at API or collector boundary; do not rely on backend-specific flattening. | platform | TBD |
| raw `path` label | `http_route` | Normalize route before emission; readers accept legacy only during migration. | gateway | TBD |
| `consumer_id` Prometheus label | logs/traces only | Remove from Prometheus labels after reader audit. | gateway | TBD |
| `tool`, `tool_id`, `tool_name` mismatch | canonical `tool_name` | API readers support current names, then migrate to canonical projection. | platform/gateway | TBD |
| `mcp_request_duration_seconds` queries | emitted STOA MCP duration metric or recording rule | Add alias or update reader after metric audit. | platform | TBD |
| OpenSearch `resource.attributes.tenant@id` filters | canonical tenant filter | Do not assume tenant is a resource attribute unless the collector sets it. | platform | TBD |
| Grafana URL token authentication | backend-mediated session/proxy | Replace in Console productization PR. | console/platform | TBD |

## 9. Tenant-Safety Requirements

Tenant filtering MUST be enforced server-side.

The Console frontend MUST NOT be the security boundary. Any query to
Prometheus, Tempo, Loki, OpenSearch, or Grafana MUST go through a backend layer
that applies tenant authorization before executing or returning data.

Tenant filters MUST be derived from authenticated server-side context for
tenant-scoped users. User-provided tenant query parameters MAY narrow an
authorized scope, but MUST NOT expand it.

| Requirement | Expected behavior |
| --- | --- |
| Prometheus tenant isolation | A tenant-scoped user cannot query another tenant's metrics. |
| Tempo tenant isolation | A trace from tenant A cannot be fetched by tenant B. |
| Loki tenant isolation | Logs correlated to a trace preserve tenant filtering. |
| OpenSearch tenant isolation | Audit/security documents are filtered server-side. |
| Console API isolation | Tenant filters are derived from auth context, not trusted request params. |
| Grafana expert mode | Access is operator/admin only or proxied with enforced authorization. |

## 10. Sensitivity and Retention

Every telemetry data category MUST have an explicit retention policy before it
is treated as production-ready. Exact durations may differ by environment and
tenant plan, but the category, sensitivity, and owner must be documented.

| Data | Backend | Sensitivity | Default retention class | Notes |
| --- | --- | --- | --- | --- |
| Operational metrics | Prometheus | low/medium | short/medium | No payloads, no request IDs, no trace IDs as labels. |
| Traces | Tempo | medium/high | short | May expose topology, tenant, errors, and request metadata. |
| Logs | Loki | medium/high | short/medium | MUST be structured and redacted. |
| Audit events | OpenSearch | high | medium/long | Security/compliance path. |
| Forensics snapshots | OpenSearch | high | controlled | Explicit purpose only. |
| PII/guardrail events | OpenSearch or dedicated store | very high | controlled | Requires redaction, access control, and owner approval. |
| Search events | OpenSearch | medium/high | product-specific | May contain customer identifiers. |

Telemetry MUST NOT include secrets, raw credentials, bearer tokens, API keys,
private keys, password material, or unredacted payloads.

## 11. Sampling Policy Direction

This contract does not change sampling behavior. Future sampling changes SHOULD
prefer collector-side tail sampling where operationally possible.

The target policy SHOULD support:

- 100% retention for errors;
- 100% retention for slow requests above a documented threshold;
- 100% retention for critical security and guardrail events;
- low sampling for nominal traffic;
- temporary tenant or gateway overrides during incidents;
- no payload-sensitive data in sampled spans or logs.

Head sampling in services MAY be used as a cost guardrail, but it SHOULD NOT be
the only mechanism for product-critical call flow visibility.

## 12. Console Product Model

The Console observability product SHOULD be organized around user intent, not
backend inventory.

| View | Audience | Primary source | Objective |
| --- | --- | --- | --- |
| Gateway Health | client + operator | Prometheus/API | "Is it working?" |
| Live Calls | client limited + operator | Tempo/Loki via API | "What happened?" |
| Security & Guardrails | client/admin security | OpenSearch/audit | "What was blocked or exposed?" |
| Grafana Expert | internal/operator | Grafana | Deep debugging. |

Grafana MAY remain available for expert/operator workflows, but it SHOULD NOT
be the default product UI for tenant users. Console dashboards MUST use backend
authorization and MUST NOT rely on frontend-only tenant filtering.

## 13. Golden Debugging Path

The target operator journey is:

1. receive a p95 latency or availability alert;
2. open Gateway Health;
3. filter by authorized tenant and gateway;
4. find a slow or failed request;
5. open the Tempo trace;
6. navigate to correlated Loki logs using `trace_id`;
7. inspect guardrail/security/audit context where authorized;
8. explain the incident without manually querying five systems.

Future implementation PRs SHOULD add smoke tests that validate this path for
gateway, sidecar, and stoa-connect traffic.

## 14. Acceptance Criteria for PR 1A

This contract is accepted when:

- every canonical field has a documented projection for OpenTelemetry,
  Prometheus, logs JSON, and Console API;
- every Prometheus label is either allowed, limited, or forbidden;
- `tenant_id` usage in Prometheus is explicitly limited to client-facing/SLO
  metrics;
- `consumer_id`, `trace_id`, `span_id`, request IDs, and raw paths are
  forbidden as Prometheus labels;
- tenant-safety requirements are defined as testable behaviors;
- legacy names are inventoried with a compatibility strategy;
- OpenSearch is documented as audit/security/search/forensics, not the primary
  live observability path;
- Grafana is documented as expert/operator mode, not the default product
  Console;
- no production pipeline, emitted metric, authorization behavior, or UI behavior
  is changed by this PR.

## 15. References

- Prometheus metric and label naming:
  https://prometheus.io/docs/practices/naming/
- OpenTelemetry semantic conventions:
  https://opentelemetry.io/docs/concepts/semantic-conventions/
- OpenTelemetry service attributes:
  https://opentelemetry.io/docs/specs/semconv/registry/attributes/service/
- Grafana Tempo trace-to-logs correlation:
  https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-logs/
