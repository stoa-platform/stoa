# CAB-2213 Council Stage 2 Findings

Date: 2026-05-11
Scope: CAB-2213 master MEGA, CAB-2214 Phase 6.0 gate
Verdict: `go`
Score: `8.0/10`
Threshold: `>= 8.0`

## References

- Plan: `docs/plans/2026-05-11-guardrails-non-mcp-4b-full.md`
- Decision log: `docs/decisions/2026-05-11-guardrails-non-mcp-4b-full.md`
- Source plan: `docs/plans/2026-05-09-observability-data-visibility.md`
- Source decision log: `docs/decisions/2026-05-09-observability-data-visibility.md`

## Council Context

Council Stage 2 ran after external HEG-PAT-022 validation and before any
implementation behavior. The plan frontmatter locks `impact_score: HIGH` and
`council_review_required: true`, so Council >= 8.0/10 is required before Phase
6.1+ implementation work may merge.

## 8-Persona Scoring

| Persona | Score | Verdict | Summary |
| --- | ---: | --- | --- |
| Chucky | 9/10 | Go | Risks, anti-goals, ACs, DAG, rollback, and A13 close the absent-series trap. |
| N3m0 | 8/10 | Go | AR-1 is preserved; backend owns state; no new UI surface. |
| Gh0st | 9/10 | Go | No new dependency required by the plan; standard SBOM CI remains sufficient. |
| Pr1nc3ss | 7/10 -> 8/10 | Fix -> Go | E6 bounds `stale_reason`, removing the Prometheus topology leak risk. |
| OSS Killer | 8/10 | Go | Enterprise value is credible; `ws_proxy` conditional scope avoids over-build. |
| Archi 50x50 | 9/10 | Go | Abstractions, compatibility window, binary ACs, and A13 statefulness align. |
| Better Call Saul | 9/10 | Go | A12/A18 avoid real PII; no tenant label; aggregated counters remain GDPR-safe. |
| Gekk0 | 8/10 | Go | Enterprise differentiator; OSS empty states remain honest; GTM claim is clear. |

## Computation

Initial score before E6:

- Persona average: `(9+8+9+7+8+9+9+8)/8 = 8.375/10`
- HIGH impact modifier: `-0.5`
- Final: `7.875/10`, verdict `fix`

After E6:

- Pr1nc3ss re-score: `7/10 -> 8/10`
- Persona average: `(9+8+9+8+8+9+9+8)/8 = 8.5/10`
- HIGH impact modifier: `-0.5`
- Final: `8.0/10`, verdict `go`

## E6 Rationale

Risk identified: `stale_reason` as a free-form string could leak Prometheus
hostnames, internal URLs, raw error text, query traces, or topology details to
UI consumers.

Lock applied:

```ts
type StaleReason =
  | "prom_unreachable"
  | "scrape_gap"
  | "producer_absent"
  | "stale_unknown";
```

Backend mapping and UI rendering rules were added to plan E6. Phase 6.4 DoD and
AC-17 require tests proving `stale_reason` never contains raw Prometheus errors,
hostnames, internal URLs, or query traces.

## Deferred Non-Blocking Adjustments

- N3m0: Phase 6.5 accessibility checklist for keyboard navigation, ARIA live
  regions, and screen reader announcements.
- Archi 50x50: retire `deployment_mode="unknown"` in a follow-up plan once mode
  detection is reliable.
- Gekk0: add Phase 6.6 release-note checklist for sales/marketing comms.
