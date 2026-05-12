# Phase 6 Smoke Fixtures

These fixtures are the only approved Phase 6.6 guardrails smoke payloads.
They are synthetic markers, not customer prompts, and contain no emails, phone
numbers, payment numbers, government identifiers, real person names, or customer
records.

Prod runs must use the synthetic tenant and route name `guardrails-probe`.
Operators review this file before each prod smoke.

| Fixture | Surface | Guardrail | Decision | Payload |
| --- | --- | --- | --- | --- |
| `mcp-allow` | `mcp` | `pii` | `allow` | `{"text":"STOA_SYNTH_ALLOW_ALPHA"}` |
| `mcp-redact` | `mcp` | `pii` | `redact` | `{"text":"STOA_SYNTH_REDACT_ALPHA"}` |
| `mcp-block-injection` | `mcp` | `injection` | `block` | `{"text":"STOA_SYNTH_INJECTION_BLOCK_ALPHA"}` |
| `mcp-error` | `mcp` | `prompt_guard` | `error` | `{"text":"STOA_SYNTH_POLICY_ERROR_ALPHA"}` |
| `api-observe-allow` | `api_proxy` | `content_filter` | `allow` | `{"probe":"guardrails-probe","text":"STOA_SYNTH_API_OBSERVE_ALPHA"}` |
| `dynamic-observe-trip` | `dynamic_proxy` | `content_filter` | `block` | `{"probe":"guardrails-probe","text":"STOA_SYNTH_DYNAMIC_TRIP_ALPHA"}` |

Dev/k3d state evidence:

| State | Controlled setup |
| --- | --- |
| `metrics_unavailable` | Control Plane API points at stopped/unreachable dev Prometheus. |
| `no_evaluations` | Clean dev/k3d or isolated gateway before guardrail-applicable traffic. |
| `evaluations_zero_trips` | Allow-only traffic from `mcp-allow` and `api-observe-allow`. |
| `trips_observed` | Deterministic trip from `mcp-redact`, `mcp-block-injection`, or `dynamic-observe-trip`. |
| `stale_data` | Dev-only scrape pause after a successful fresh scrape. |

Production safety lock:

- Validate only `evaluations_zero_trips` or `trips_observed`.
- Do not stop Prometheus, isolate a fresh environment, or pause scraping in prod.
- Do not substitute real customer prompts for these markers.
- Drop or filter probe traces with `probe=guardrails-probe` after the run.
