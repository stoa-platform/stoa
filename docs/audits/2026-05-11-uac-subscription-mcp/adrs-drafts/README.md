# ADR drafts — UAC Subscription + MCP corrective

This folder stages **5 draft ADRs** produced after the 2026-05-11 audit and the 2026-05-13 challenger verdict (`GO_WITH_CONDITIONS`).

They are **not yet in `stoa-docs/docs/architecture/adr/`** because:

1. They depend on signed acceptance of the 7 challenger conditions (C1–C7) in the corrective plan.
2. They cite each other as companions; promoting one without the others breaks the doctrine.
3. The current `stoa-docs` branch (`chore/cab-2137-security-deps`) is unrelated; ADR promotion must happen on a dedicated branch.

## Inventory

> **Solo project mode** — the "Sign-off owner" column below was originally written with separate DPO / Legal / Security / Business / Product / Gateway / CP-API roles. Those roles **do not have separate humans** on this project. All decisions are made by the operator (founder) acting in those roles for this project stage. See memory `feedback_solo_project_mode_signoffs.md`.

| ADR | Title | Depends on (other drafts) | Sign-off owner |
|-----|-------|---------------------------|----------------|
| ADR-067 | UAC Describes / MCP Projects / Smoke Proves | — | Operator |
| ADR-068 | Audit Log Actor/Resource/Action Doctrine | ADR-069 (coupled) | Operator |
| ADR-069 | GDPR ↔ DORA Audit Reconciliation | ADR-068 (coupled) | Operator (non-delegable to AI — the operator personally decides) |
| ADR-070 | Gateway Fail-Closed Posture | ADR-067, ADR-068 | Operator (accepting product SLA impact) |
| ADR-071 | API Subscription Lifecycle | ADR-067, ADR-068, ADR-070 | Operator |

## Promotion checklist (per ADR)

Before moving a file into `stoa-docs/docs/architecture/adr/`:

- [ ] Operator approval recorded on the Linear ticket (single APPROVED / BLOCKED / DEFER verdict, one-line rationale)
- [ ] Companion ADRs at least at Proposed status (or co-promoted)
- [ ] Section "Open questions" answered or recorded as accepted-with-defaults
- [ ] Cross-references to corrective plan and decision record updated to point at canonical paths
- [ ] Promotion PR opens on a dedicated branch in `stoa-docs`

## Doctrinal notes

- ADR-001 already exists in stoa-docs (Accepted, 2026-01-18) and covers the **architecture** of Third-Party API exposure. It is **not** amended by this batch. ADR-071 extends it for the subscription lifecycle inside that architecture.
- ADR-066 already exists (Proposed, 2026-04-25) and defines the **fields** of the LLM metadata on UAC. ADR-067 is the **enforcement doctrine** on top.
- ADR-068 and ADR-069 are **coupled**: promoting ADR-068's immutability trigger without ADR-069's pseudonymization model breaks the current `erase_user_pii()` code path. They must move together.
- ADR-070 enforces fail-closed; that is a **product decision** with availability impact and requires Business sign-off, not just Security.

## References

- Audit: [../AUDIT-RESULTS.md](../AUDIT-RESULTS.md)
- Plan: [../../../plans/2026-05-11-uac-subscription-mcp-corrective.md](../../../plans/2026-05-11-uac-subscription-mcp-corrective.md)
- Decision record: [../../../decisions/2026-05-11-uac-subscription-mcp-corrective.md](../../../decisions/2026-05-11-uac-subscription-mcp-corrective.md)
