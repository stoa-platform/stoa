---
id: plan-2026-05-10-guardrails-runtime-truth-contract
validation_status: validated
plan_ref: docs/plans/2026-05-07-observability-data-integrity.md
source_evidence:
  - docs/audits/2026-05-07-observability/AUDIT.md
---

# PR-3A — Guardrails Runtime Truth Contract
## Context

This mini-spec locks the runtime truth contract for `/observability/security` before PR-3 implementation. It elaborates Annex B in `docs/plans/2026-05-07-observability-data-integrity.md` without changing AR-1 or AR-2.

Root bug: the current UI can collapse unknown guardrail metrics into `0`, which makes disabled, enabled-with-zero-events, stale, and broken data sources look identical.
## Scope

In scope:
- `GET /v1/admin/gateways/guardrails/config`.
- Guardrails metrics shape under `GET /v1/admin/gateways/metrics`.
- Freshness, `null` vs `0`, disabled vs enabled+0, stale vs error semantics.
- Time range behavior for metrics and guardrails events.
- Rate Limit ownership per AR-2.
- Security Posture vs Security & Guardrails wording per AR-1.

Out of scope:
- Code implementation.
- Security Posture backend changes.
- Navigation/sidebar cleanup beyond the AR-1 wording contract.
- Moving Rate Limit into Live Calls.
- New OPA policy event ingestion.
## Canonical product decisions

AR-1 is already validated in the canonical plan: do not merge Security Posture and Security & Guardrails. Use distinct scopes and wording:

| Route | Title | Subtitle |
|---|---|---|
| `/observability/security` | Security & Guardrails | Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring |
| `/security-posture` | Security Posture | Compliance findings, security score, configuration assessment |

AR-2 is already validated in the canonical plan: Rate Limit belongs to Security & Guardrails because rate limiting is a protection outcome, not a traffic-volume signal. Live Calls may expose traffic, latency, and errors, but does not own rate-limit guardrail truth.
## Endpoint: `GET /v1/admin/gateways/guardrails/config`

Returns the effective guardrail enablement state used by the running gateway/control-plane integration.

```json
{
  "pii_enabled": true,
  "injection_detection_enabled": true,
  "prompt_guard_enabled": true,
  "content_filter_enabled": true,
  "rate_limit_enabled": true,
  "opa_policy_enabled": true,
  "source": "env",
  "updated_at": "2026-05-10T00:00:00Z"
}
```

Field rules:

| Field | Type | Semantics |
|---|---|---|
| `pii_enabled` | boolean | Effective PII detection runtime/config state. |
| `injection_detection_enabled` | boolean | Effective prompt injection detection runtime/config state. |
| `prompt_guard_enabled` | boolean | Effective prompt guard runtime/config state. |
| `content_filter_enabled` | boolean | Effective content filtering runtime/config state. |
| `rate_limit_enabled` | boolean | Effective rate-limit protection runtime/config state. |
| `opa_policy_enabled` | boolean | Effective OPA policy evaluation runtime/config state. |
| `source` | `"env" \| "runtime" \| "config-service"` | Authority used for the values in this response. |
| `updated_at` | ISO-8601 UTC string | Time at which the backend last evaluated or refreshed this config state. |

`source` values:
- `env`: values are derived from environment/config values visible to the control plane or gateway process.
- `runtime`: values are derived from a live gateway runtime/admin endpoint.
- `config-service`: values are derived from a config service that is authoritative for the gateway.

Config booleans are not UI preferences. They are the backend's best statement of the effective runtime state. The response must not use `null` for config booleans; if the backend cannot determine the state, the request should fail instead of returning guessed booleans.
## Guardrails metrics response

`GET /v1/admin/gateways/metrics?range=<range>` must include the guardrails object below. The object may be returned by the existing metrics endpoint or by a compatible sibling endpoint, but `/observability/security` consumes these exact field names.

```json
{
  "guardrails": {
    "pii_detections": 0,
    "injection_blocks": 0,
    "prompt_guard_blocks": 0,
    "content_filter_blocks": 0,
    "rate_limit_blocks": 0,
    "last_sample_at": "2026-05-10T00:00:00Z",
    "metrics_age_seconds": 12,
    "source_healthy": true
  }
}
```

Type contract:

```ts
{
  guardrails: {
    pii_detections: number | null,
    injection_blocks: number | null,
    prompt_guard_blocks: number | null,
    content_filter_blocks: number | null,
    rate_limit_blocks: number | null,
    last_sample_at: string | null,
    metrics_age_seconds: number | null,
    source_healthy: boolean
  }
}
```

Metric-to-config mapping:

| Metric field | Config owner |
|---|---|
| `pii_detections` | `pii_enabled` |
| `injection_blocks` | `injection_detection_enabled` |
| `prompt_guard_blocks` | `prompt_guard_enabled` |
| `content_filter_blocks` | `content_filter_enabled` |
| `rate_limit_blocks` | `rate_limit_enabled` |

`opa_policy_enabled` is config-only in this contract. Adding OPA runtime counters later is a contract change and must not be hidden inside an existing metric.
## Freshness semantics

Freshness describes the metrics source, not the guardrail config source.

| Field | Rule |
|---|---|
| `last_sample_at` | ISO-8601 UTC timestamp of the newest metrics sample used for the guardrails values. `null` means no usable sample was returned. |
| `metrics_age_seconds` | Backend-computed age of `last_sample_at` at response time. `null` iff `last_sample_at` is `null`. |
| `source_healthy` | `true` when the metrics query succeeded and the response was interpretable. `false` when the metrics backend/query failed or returned an invalid response. |

Stale threshold: metrics are stale when `source_healthy=true`, `last_sample_at` is not `null`, and `metrics_age_seconds > 60`.

Precedence:
1. Backend transport error or invalid response: UI renders "Metrics unavailable".
2. Feature disabled by config: UI renders "Disabled".
3. `source_healthy=false`: UI renders "Metrics unavailable".
4. `last_sample_at=null` or the card's count is `null`: UI renders "No metrics sample".
5. `metrics_age_seconds > 60`: UI renders "Stale metrics".
6. Healthy numeric value: UI renders the count and latest sample context.
## `null` vs `0` semantics

`0` means the metrics source was healthy and the backend can prove that zero matching events occurred for the selected time range.

`null` means unknown, unavailable, not sampled, or not safely distinguishable from absent instrumentation. The backend must preserve `null`; the frontend must not coerce it to `0`.

Forbidden UI pattern:

```ts
metrics?.guardrails?.pii_detections || 0
```

Required UI pattern:

```ts
const count = metrics?.guardrails?.pii_detections;
if (count === null || count === undefined) {
  return "No metrics sample";
}
return `${count} events`;
```
## Disabled vs enabled+0

Disabled state comes from `GET /v1/admin/gateways/guardrails/config`. A disabled feature is rendered as disabled even if the metrics payload contains `0` or `null` for the corresponding counter.

Enabled+0 means the feature is enabled, the metrics source is healthy and fresh, and the corresponding count is exactly `0`.

Required UI state rules:

| State | Required rendering |
|---|---|
| enabled + healthy + `0` | "0 events · last sample ..." |
| disabled | "Disabled" |
| `null` sample | "No metrics sample" |
| stale | "Stale metrics" |
| backend error | "Metrics unavailable" |

The UI may include icons, colors, or relative timestamps, but the visible semantic text above must be present.
## Stale vs error

Stale is a successful read of old metrics. Error is a failed read.

| Condition | Meaning | UI |
|---|---|---|
| HTTP request fails, times out, or response is invalid | Metrics backend unavailable or contract broken | "Metrics unavailable" |
| `source_healthy=false` | Metrics backend/query failed behind a successful API response | "Metrics unavailable" |
| `source_healthy=true`, `last_sample_at=null` | Query worked but no sample exists | "No metrics sample" |
| `source_healthy=true`, `last_sample_at!=null`, `metrics_age_seconds > 60` | Source is reachable but sample is too old | "Stale metrics" |

The UI must not render stale as an error, and must not render an error as stale.
## Time range behavior

Supported ranges are aligned with Live Calls:

```text
1h / 6h / 24h / 7d
```

Rules:
- The selected range is passed to `GET /v1/admin/gateways/metrics`.
- The selected range is passed to `GET /v1/admin/gateways/metrics/guardrails/events` if the events endpoint supports range filtering; if not, PR-3 must add or document equivalent behavior before showing a range selector for events.
- Counts reflect the selected range only.
- `last_sample_at` and `metrics_age_seconds` describe the newest metrics sample used, not the range start or end.
- `GET /v1/admin/gateways/guardrails/config` is not range-dependent and must not be refetched solely because the time range changed.
- Empty query results are `0` only when the metrics source is healthy and the backend can prove no events occurred in the selected range. Otherwise they remain `null`.
## Rate Limit ownership per AR-2

Rate Limit stays in Security & Guardrails.

Implementation constraints for PR-3:
- The Rate Limit card is backed by `rate_limit_enabled` and `rate_limit_blocks`.
- If clickable, it must filter to `rate-limit` events.
- If no reliable rate-limit event stream exists, the card must be non-clickable or show an explicit empty state such as "No rate-limit events".
- It must never route through a synthetic `all` filter that silently changes semantics.
## Acceptance criteria

- [ ] `GET /v1/admin/gateways/guardrails/config` returns the documented shape and real effective booleans.
- [ ] Guardrails metrics expose `last_sample_at`, `metrics_age_seconds`, and `source_healthy`.
- [ ] `null` is preserved and is never collapsed into `0`.
- [ ] UI distinguishes disabled, enabled+0, no sample, stale, and error.
- [ ] Time range selection affects guardrails metrics and events consistently.
- [ ] Rate Limit remains in Security & Guardrails per AR-2.
- [ ] `/observability/security` and `/security-posture` use the AR-1 wording exactly.
## Required tests for PR-3 implementation

Backend:
- Config endpoint returns the exact response shape.
- Metrics endpoint preserves `null` vs `0`.
- Metrics endpoint includes freshness fields.
- Source failure returns `source_healthy=false` or an API error, never fake zeroes.

Frontend:
- Config panel renders enabled/disabled states from `/guardrails/config`.
- Cards render enabled+0, enabled+N, disabled, no-sample, stale, and error states.
- Time range selector propagates to metrics and guardrails events fetches.
- Rate Limit does not use a synthetic `all` filter.
- Page title/subtitle match AR-1 wording.
