# PR 1B PromQL Compatibility Inventory

This inventory is the implementation handoff from
`docs/observability/telemetry-contract.md` to reader-side PromQL compatibility.

Scope for PR 1B:

- inventory API/Console-facing PromQL readers;
- compare queried metrics with metrics emitted by gateway/control-plane/stoa-connect;
- add old + new reader compatibility where a safe compatibility path exists;
- add tests that fail when API queries drift back to missing metric names or
  forbidden label assumptions.

Out of scope:

- Console redesign;
- OpenTelemetry, Loki, Tempo, OpenSearch, Fluent Bit, Data Prepper, or Alloy
  pipeline changes;
- gateway cardinality cleanup;
- sidecar or stoa-connect wiring changes.

## Reader Inventory

| Reader | Query target | Producer status | Contract status | PR 1B action |
| --- | --- | --- | --- | --- |
| `PrometheusClient.get_request_count` | `stoa_mcp_tools_calls_total` | Emitted by Rust gateway with `tool`, `tenant`, `status`. PR 2 removed the forbidden `consumer_id` label. | Legacy labels; compatible reader needed. | Read legacy `tenant` and canonical `tenant_id`. Keep `subscription_id` behavior for DB fallback until producer support exists. |
| `PrometheusClient.get_success_count` | `stoa_mcp_tools_calls_total{status="success"}` | Emitted by Rust gateway. | Legacy labels; compatible reader needed. | Read legacy `tenant` and canonical `tenant_id`. |
| `PrometheusClient.get_error_count` | `stoa_mcp_tools_calls_total{status=~"error\|timeout"}` | Emitted by Rust gateway. | Legacy labels; compatible reader needed. | Read legacy `tenant` and canonical `tenant_id`. |
| `PrometheusClient.get_avg_latency_ms` | `mcp_request_duration_seconds_*` | Not emitted by current Rust gateway. Current metric is `stoa_mcp_tool_duration_seconds_*`. | Missing/renamed. | Prefer emitted `stoa_mcp_tool_duration_seconds_*`; keep `mcp_request_duration_seconds_*` as read-side legacy alias. |
| `PrometheusClient.get_top_tools` | `stoa_mcp_tools_calls_total` grouped by `tool_id`, `tool_name` | Gateway emits `tool`, not `tool_id` or `tool_name`. | Label mismatch. | Normalize legacy `tool` to canonical `tool_name`; read canonical `tool_name` when present. |
| `PrometheusClient.get_daily_calls` | `stoa_mcp_tools_calls_total{tenant=~"...\|default"}` | Emitted by Rust gateway. | Legacy default fallback violates exact tenant matching. | Read exact legacy `tenant` and canonical `tenant_id`; no `\|default` regex. |
| `PrometheusClient.get_tool_success_rate` | `tool_id`, `user_id`, `tenant_id` labels | Gateway emits `tool`, `tenant`, `status`. | Label mismatch. | Read legacy `tool`/`tenant` and canonical `tool_name`/`tenant_id`; do not query `user_id` or `tool_id`. |
| `PrometheusClient.get_tool_avg_latency` | `mcp_request_duration_seconds_*` with `tool_id`, `user_id`, `tenant_id` | Not emitted by current Rust gateway. | Missing/renamed and label mismatch. | Prefer emitted `stoa_mcp_tool_duration_seconds_*`; keep legacy metric alias; read legacy/canonical labels. |
| `routers.usage` token endpoints | `stoa_mcp_gateway_tokens_by_tenant`, `stoa_mcp_gateway_transformer_reduction_ratio` | No matching producer found in current gateway scan. | Missing. | Keep endpoint behavior but restore `PrometheusClient._query` and validators so missing metrics degrade through Prometheus results instead of runtime `AttributeError`. |
| LLM cost methods | `gateway_llm_*` | Partially emitted by Rust gateway with provider/model labels; token/request totals are incomplete. | Partial. | No tenant-unsafe fallback to unscoped metrics in PR 1B. Leave broader LLM metric contract to a follow-up. |
| `GatewayMetricsService._fetch_guardrails_metrics` | `stoa_guardrails_*`, `stoa_prompt_guard_detected_total` | Emitted by Rust gateway; PII metric has `action`, injection has `tool`, content filter has `action/category`. | Partial label mismatch for PII by tool. | Leave for guardrails-specific follow-up; do not add high-cardinality tool labels to PII metric in PR 1B. |
| Console direct Prometheus hooks | UI-owned query strings | Mixed. Some queries still use raw `path`. | Productization/cardinality scope. | Out of scope for PR 1B; covered by PR 5 and gateway cardinality PR. |

## Compatibility Rule Applied

PR 1B only adds reader-side compatibility. It does not rename emitted metrics.

For MCP usage metrics, API readers now prefer the current emitted gateway metric
names and support the canonical label projection from the contract:

- current labels: `tenant`, `tool`
- canonical labels: `tenant_id`, `tool_name`

Where both old and new exist during a migration window, PromQL uses `or` rather
than summing both branches to avoid double counting.
