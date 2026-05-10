# Control-plane audit pipeline probe

Plan: `docs/plans/2026-05-09-observability-data-visibility.md`; phase: 5A. Decisions:
`docs/decisions/2026-05-09-observability-data-visibility.md`,
`docs/decisions/2026-05-09-seed-vs-runtime-contract.md`,
`docs/audits/2026-05-09-observability-data-visibility/probe-trace-walk.md`.

Implementation shape: Option A, `control-plane-api/scripts/probes/audit_pipeline_probe.py`.
The probe validates only:

```text
control-plane action -> Kafka audit topic -> audit_trail_consumer -> audit_events -> /v1/audit/{tenant}
```

It creates one API under fixed tenant `audit-probe`, sends `X-Probe-Id`, observes
the matching envelope on `stoa.audit.trail` (`Topics.AUDIT_LOG`), waits for
`audit_events`, then checks `/v1/audit/audit-probe`.

Required binary hops:

- `audit_emit`: `POST /v1/tenants/audit-probe/apis` returns the expected API.
- `kafka_consumed`: the probe consumes the matching `audit` envelope from Kafka.
- `pg_persisted`: a matching row appears after `audit_trail_consumer` runs.
- `api_visible`: `/v1/audit/audit-probe?search=<api_id>` returns the event.

This PR validates the control-plane audit path only; gateway telemetry traces are
Phase 5B and gated by Phase 0 verdict. It does not prove gateway runtime
telemetry, Prometheus metrics, Tempo/OpenSearch traces, Phase 2 fixtures, or
end-to-end trace visibility.

- Fixed tenant `audit-probe`; never `demo`, `free-aech`, or customer tenants.
- Probe API rows and matching audit rows are deleted at the end.
- If `audit-probe` is absent, a minimal tenant row is created and cleaned up.
- Phase 2 fixture markers are untouched: no `details.synthetic=true`, no `fixture_batch`.
- `ENVIRONMENT=production` refuses unless `OPERATOR_OPT_IN` is `1`, `true`, `yes`, `y`, `on`, or `operator-approved`.
- No workflow, schedule, or cron is added; Q8.4 remains on-demand/manual.

Usage: set `ENVIRONMENT`, `STOA_CONTROL_PLANE_API_URL`, `STOA_API_TOKEN`,
`DATABASE_URL`, and `KAFKA_BOOTSTRAP_SERVERS`, then run
`python control-plane-api/scripts/probes/audit_pipeline_probe.py`.
