---
title: "Operator approvals — CAB-2225..2229 (solo project mode)"
date: 2026-05-13
mode: solo
operator: "founder, acting as product / security / privacy / legal / business decision owner"
verdict_summary: "5/5 APPROVED with conditions"
related_decision_record: "docs/decisions/2026-05-11-uac-subscription-mcp-corrective.md"
related_plan: "docs/plans/2026-05-11-uac-subscription-mcp-corrective.md"
related_audit: "docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md"
---

# Operator approvals — CAB-2225..2229 (solo project mode)

> **Solo project mode.** No separate DPO / Legal / Security / Business / Product / Gateway / CP-API human exists at this stage. The operator (founder) is the single decision-maker acting in all those roles. All approvals below are recorded as
> *"APPROVED by operator acting as product, security, privacy, legal, and business decision owner for this solo project stage."*
> They are **not** to be represented as "DPO approved", "Legal approved", "Security approved", or any other multi-role fan-out.
> See memory rule `feedback_solo_project_mode_signoffs`.

This document is the canonical regulatory trace that the policies in ADR-067, ADR-068, ADR-069, ADR-070, ADR-071 came from the human operator — not from Claude or Codex. Agents may proceed within the accepted scope only; any deviation requires re-challenge.

---

## CAB-2225 — ADR-067 UAC describes / MCP projects / Smoke proves

**Verdict:** APPROVED by operator acting as product, security, privacy, legal, and business decision owner for this solo project stage.

**Date:** 2026-05-13.

**Scope accepted:** Typed UAC projection in `tools/list` (`side_effects` / `requires_human_approval` / `safe_for_agents` typed on the wire), runtime enforcement at the gateway (`tools/call` refused when `requires_human_approval=true` and no valid approval token is presented), smoke gate blocking on UAC publish.

**Mandatory conditions (binding on Codex):**

1. Approval token invariants stay mandatory, in full — `jti` single-use atomic, `arguments_hash`, `policy_version`, `contract_version`, `requester_actor_id` distinct from `approver_actor_id`, plus the three audit events `APPROVAL_TOKEN_ISSUED` / `APPROVAL_TOKEN_USED` / `APPROVAL_TOKEN_REJECTED`.
2. Smoke gate must remain blocking before any UAC publish. No soft-mode allowed at publish time.
3. No silent fallback may mark an unsafe tool `safe_for_agents=true`. Malformed metadata is an error, not a warning.

**Rationale:** Typed UAC projection plus runtime approval-token enforcement plus smoke gate is the only configuration that lets the doctrine be auditable end-to-end. Anything weaker manufactures paper compliance.

---

## CAB-2226 — ADR-068 (audit immutability) + ADR-069 (GDPR ↔ DORA reconciliation), joint

**Verdict ADR-068:** APPROVED by operator acting as product, security, privacy, legal, and business decision owner for this solo project stage.

**Verdict ADR-069:** APPROVED by operator acting as product, security, privacy, legal, and business decision owner for this solo project stage.

**Date:** 2026-05-13.

**Pseudonymization key disposition:** **retrievable-with-dual-control** (per ENISA, preserves forensic/legal recovery under controlled access).

**Vault wrap decision:** **implement Vault wrap NOW**. The `_wrap_pseudonymization_key` seam currently in PR #2781 (commit `8fd8ba729`) is a placeholder; it MUST be upgraded to a real Vault transit-engine envelope (or equivalent) BEFORE PR #2781 may merge. Raw storage without Vault wrap is **NOT accepted** as the final state.

**Mandatory conditions (binding on Codex):**

1. Audit-source row in `audit_events` remains immutable — PG trigger is the floor, application-level "never UPDATE audit_events" is the ceiling.
2. GDPR Art.17 erasure goes through `pseudonymized_audit_erasures` + `audit_events_redacted` view. No mutation of the source row, ever.
3. Vault wrap of `pseudonymization_key` must land before PR #2781 may exit DRAFT. The Vault path uses dual-control retrieval (two operator-held secrets / two-actor approval recorded in the audit chain) so that re-identification is auditable.
4. If at any future point the operator chooses to accept raw storage (DB = full trust boundary), it requires a NEW ADR explicitly narrowing the trust boundary and accepting that risk in writing. **This decision record does NOT pre-authorize that path.**

**Rationale:** Audit immutability and GDPR erasure must coexist. The auxiliary-table + redaction-view model achieves it. Retrievable-with-dual-control preserves the forensic/legal recovery story without making re-identification trivial. Vault wrap closes the obvious "DB compromised = pseudonymization broken" gap and is cheap to add now while the seam exists.

---

## CAB-2227 — ADR-070 gateway fail-closed posture

**Verdict:** APPROVED by operator acting as product, security, privacy, legal, and business decision owner for this solo project stage.

**Date:** 2026-05-13.

**Parameters accepted:**

| Parameter | Operator decision |
|-----------|-------------------|
| Max cache TTL during CP outage | **60 minutes**. Outage bridge only — not an extensible policy source. |
| Phase 0 audit emit scope | **C1 Option A — denies + approval-gated only** with durable spool. |
| Tenant-visible `/status` endpoint during fail-closed | **Yes**. Exposes degraded state only — never secrets, never policy internals. |

**Mandatory conditions (binding on Codex):**

1. CP unreachable AND no fresh signed cache → deny.
2. Policy load failure at boot → process exits non-zero. Readiness FAIL. No permissive fallback.
3. Permission absent from cache → deny.
4. Revocation event invalidates cache **immediately**, even if cache has not expired. Revocation priority beats every cached allow.
5. `requires_human_approval=true` without a valid approval token → deny (ties into CAB-2225 enforcement).
6. Readiness probe reflects actual enforcement state (policy bundle valid + CP reachable in window OR signed cache valid + audit spool below high-water).
7. Durable spool required for audit events. **No silent drop** — if replay cannot happen, declare an `audit_gap_declared` incident, do not just bump a counter.
8. Cache TTL is **never extensible locally** by the gateway. Re-issuance is CP-driven only.

**Rationale:** Fail-closed is the right default for UAC/runtime authorization. A 60-minute signed-cache ceiling is an acceptable outage bridge for a solo project's CP availability profile. Tenant-visible status reduces support load during outages without leaking policy internals.

---

## CAB-2228 — ADR-071 API subscription lifecycle

**Verdict:** APPROVED by operator acting as product, security, privacy, legal, and business decision owner for this solo project stage.

**Date:** 2026-05-13.

**Parameters accepted:**

| Parameter | Operator decision |
|-----------|-------------------|
| `PARTIALLY_PROVISIONED` visibility | **Consumer-visible, with target-level breakdown** (not a vague global state). |
| 4-eyes for destructive endpoints | **Strict — two distinct tenant-admins**. One tenant-admin + one devops is **not accepted**. |
| Time budget before `PROVISIONING_FAILED` | **15 minutes**, configurable per tenant in future. |

**Mandatory conditions (binding on Codex):**

1. `PARTIALLY_PROVISIONED` must surface target-by-target ack status to the consumer — not just a global degraded label.
2. 4-eyes enforcement must verify **distinct human subjects** at the policy layer; technical equality of actor IDs is not sufficient evidence of separation. Audit events must record both actors.
3. Every lifecycle transition emits one `audit_events` row per ADR-068 schema. Per-target updates emit `subscription_target` rows.
4. `DEPROVISIONING_FAILED` and `SUSPENDED` remain first-class degraded states (already partially delivered by PR #2782 and PR #2784).

**Rationale:** Consumers need operational truth. Hiding partial provisioning behind a green light produces support escalations and erodes trust. Destructive operations (revoke, deprovision, suspend) affect access and potentially billing — strict 4-eyes is the correct posture for a regulated API gateway. 15 minutes is a generous but reasonable provisioning ceiling.

---

## CAB-2229 — Plan integration gate

**Verdict:** PROCEED — once the four operator approvals above are recorded in repo (this document + the per-ticket Linear comments) AND the framing PR `chore/cab-2225-solo-mode-framing` lands on `main`.

**Mechanical implication:** the plan `docs/plans/2026-05-11-uac-subscription-mcp-corrective.md` may flip:

```yaml
validation_status: validated      # was: challenged
validated_at: "2026-05-13"
validated_by: "operator (solo project mode)"
validated_for_code_execution: true
conditions_pending: false  # but bound by the conditions in this decision record
```

The flip is **not** part of the framing PR per the operator's instruction (no side-effect bundling). A separate small PR closes CAB-2229 once the framing PR is on `main`.

---

## Implications for in-flight PRs

| PR | Status before | Status after this record | Next action |
|----|---------------|--------------------------|-------------|
| #2780 (alembic 107 DRAFT) | DRAFT awaits sign-off | DRAFT, sign-off resolved; awaits Vault wrap on #2781 | Hold |
| #2781 (Codex iter2 audit chain code DRAFT) | DRAFT awaits sign-off + Vault decision | DRAFT, sign-off resolved; **`_wrap_pseudonymization_key` must be upgraded to real Vault wrap before exiting DRAFT** | Codex iter3: implement Vault wrap |

Lock-step deploy ordering unchanged: code PR (#2781) merges + deploys BEFORE schema PR (#2780) on every environment.

## Anti-pattern reminder

Do **not** record any of these approvals as:
- "DPO approved"
- "Legal approved"
- "Security approved"
- "Business approved"

Use the canonical phrasing:
- "APPROVED by operator acting as product, security, privacy, legal, and business decision owner for this solo project stage."

If multiple humans ever join (Legal hire, DPO appointment, etc.), this rule flips and separate sign-offs become real again — update memory `feedback_solo_project_mode_signoffs` at that point.
