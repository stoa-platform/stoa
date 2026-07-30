# ADR drafts — UAC Subscription + MCP corrective

This folder stages **5 draft ADRs** produced after the 2026-05-11 audit and the 2026-05-13 challenger verdict (`GO_WITH_CONDITIONS`).

They are **not yet in `stoa-docs/docs/architecture/adr/`** because:

1. They depend on signed acceptance of the 7 challenger conditions (C1–C7) in the corrective plan.
2. They cite each other as companions; promoting one without the others breaks the doctrine.
3. The current `stoa-docs` branch (`chore/cab-2137-security-deps`) is unrelated; ADR promotion must happen on a dedicated branch.

> **2026-05-18 — ADR renumber (+1 shift).** This batch was originally numbered ADR-067…071. Between drafting and promotion, a duplicate-`adr-060` dedup on `stoa-docs` `main` shifted every ADR ≥066 up by one, so published `stoa-docs` `main` now holds `adr-067` (UAC LLM-Optimized) and `adr-068` (Audit Log Actor/Resource Views) — colliding with this batch. The batch was renumbered **+2 into the next free slots ADR-069…073** (Gateway Fail-Closed = ADR-072). All draft files, cross-references, the corrective plan, and the two decision records were updated. Verify the `stoa-docs` ADR index before any further promotion.

## Inventory

> **Solo project mode** — the "Sign-off owner" column below was originally written with separate DPO / Legal / Security / Business / Product / Gateway / CP-API roles. Those roles **do not have separate humans** on this project. All decisions are made by the operator (founder) acting in those roles for this project stage. See memory `feedback_solo_project_mode_signoffs.md`.

| ADR | Title | Depends on (other drafts) | Sign-off owner |
|-----|-------|---------------------------|----------------|
| ADR-069 | UAC Describes / MCP Projects / Smoke Proves | — | Operator |
| ADR-070 | Audit Log Actor/Resource/Action Doctrine | ADR-071 (coupled) | Operator |
| ADR-071 | GDPR ↔ DORA Audit Reconciliation | ADR-070 (coupled) | Operator (non-delegable to AI — the operator personally decides) |
| ADR-072 | Gateway Fail-Closed Posture | ADR-069, ADR-070 | Operator (accepting product SLA impact) |
| ADR-073 | API Subscription Lifecycle | ADR-069, ADR-070, ADR-072 | Operator |

## Promotion checklist (per ADR)

Before moving a file into `stoa-docs/docs/architecture/adr/`:

- [ ] Operator approval recorded on the Linear ticket (single APPROVED / BLOCKED / DEFER verdict, one-line rationale)
- [ ] Companion ADRs at least at Proposed status (or co-promoted)
- [ ] Section "Open questions" answered or recorded as accepted-with-defaults
- [ ] Cross-references to corrective plan and decision record updated to point at canonical paths
- [ ] Promotion PR opens on a dedicated branch in `stoa-docs`

## Doctrinal notes

- ADR-001 already exists in stoa-docs (Accepted, 2026-01-18) and covers the **architecture** of Third-Party API exposure. It is **not** amended by this batch. ADR-073 extends it for the subscription lifecycle inside that architecture.
- ADR-067 already exists (Proposed, 2026-04-25) and defines the **fields** of the LLM metadata on UAC. ADR-069 is the **enforcement doctrine** on top.
- ADR-070 and ADR-071 are **coupled**: promoting ADR-070's immutability trigger without ADR-071's pseudonymization model breaks the current `erase_user_pii()` code path. They must move together.
- ADR-072 enforces fail-closed; that is a **product decision** with availability impact and requires Business sign-off, not just Security.

## References

- Audit: [../AUDIT-RESULTS.md](../AUDIT-RESULTS.md)
- Plan: [../../../plans/2026-05-11-uac-subscription-mcp-corrective.md](../../../plans/2026-05-11-uac-subscription-mcp-corrective.md)
- Decision record: [../../../decisions/2026-05-11-uac-subscription-mcp-corrective.md](../../../decisions/2026-05-11-uac-subscription-mcp-corrective.md)
