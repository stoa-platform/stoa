# Phase 6 Rollout Findings Template

Copy this template to `docs/audits/<YYYY-MM-DD>-phase-6-rollout/findings.md`
after the operator-reviewed smoke run. Do not archive a prod finding until the
dev/k3d five-state evidence exists.

## Run Metadata

- UTC timestamp:
- Environment: `dev-k3d` or `prod`
- Workflow run:
- Operator opt-in:
- Fixture document SHA:
- Gateway version:
- Control Plane API version:

## State Verdicts

| State | Dev/k3d verdict | Prod verdict | Evidence |
| --- | --- | --- | --- |
| `metrics_unavailable` |  | forbidden |  |
| `no_evaluations` |  | forbidden |  |
| `evaluations_zero_trips` |  | pass/fail/skip |  |
| `trips_observed` |  | pass/fail/skip |  |
| `stale_data` |  | forbidden |  |

Prod verdicts are valid only for `evaluations_zero_trips` and/or
`trips_observed`. The other states must be proven in dev/k3d or staging only.

## Required Evidence

- MCP samples cover `allow`, `redact`, `block`, and `error`.
- At least one non-MCP `api_proxy` or `dynamic_proxy` observe-only sample ran.
- Gateway `/metrics` exposed full guardrails counters with only bounded labels.
- Prometheus series evidence contains no forbidden labels.
- A13 producer presence exists from a fresh zero-traffic gateway scrape.
- `/v1/admin/gateways/metrics` returned backend-derived `guardrails.state`.
- Dev/k3d AR-1 anti-regression result is green.

## Cleanup

- Probe tenant/route removed or disabled:
- Probe traces filtered/deleted from OpenSearch:
- Dashboards filtered for `guardrails-probe`:
- No production fault injection performed:

## Compatibility Window

This archive satisfies A7 condition 1 only when prod safe-state evidence is
present and dev/k3d covers the three unsafe states. Legacy counter removal still
requires the remaining A7 conditions and a separate removal plan.
