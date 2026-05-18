---
title: "ADR-071: GDPR ↔ DORA Audit Reconciliation"
sidebar_label: "ADR-071: GDPR/DORA Audit"
sidebar_position: 71
description: "Resolves the tension between GDPR Art.17 (right to erasure) and DORA Art.11 (audit log integrity / 5-year retention) by codifying a pseudonymization model with an auxiliary table that preserves the source audit row."
keywords: [ADR, GDPR, DORA, NIS2, audit log, pseudonymization, erasure, retention, compliance]
---

# ADR-071 — GDPR ↔ DORA Audit Reconciliation

## 1. Status

**Status:** Draft (operator-approved 2026-05-13 — see `docs/decisions/2026-05-13-cab-2225-2229-operator-approvals.md` §CAB-2226 for conditions; jointly with ADR-070). Key disposition: **retrievable-with-dual-control**. Vault wrap of `pseudonymization_key`: **mandatory before PR #2781 may exit DRAFT** — raw storage without Vault wrap is NOT the accepted final state. Will be promoted to `Proposed` then `Accepted` in `stoa-docs/` after CAB-2229 closes.

**Date:** 2026-05-13

**Deciders:** Operator (founder, acting as product / security / privacy / business decision owner — solo project mode; no separate DPO / Legal / Security / Business / Product role exists at this stage). The "non-delegable to AI" rule still applies — Claude and Codex must not decide GDPR/DORA reconciliation policy; only the operator can.

**Source:** `docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md` §C + cross-cutting pattern "Conflit GDPR vs DORA non résolu" + challenger decision record §C5 + §3.3 Q4.

**Related decisions:** ADR-070 Audit Log Actor/Resource/Action Doctrine (companion). ADR-072 Gateway Fail-Closed Posture (companion).

## 2. Context

STOA's audit log is the spine of DORA Art.5/8/11/17 and NIS2 Art.21 compliance. ADR-070 declares it append-only with a PostgreSQL trigger refusing `UPDATE`/`DELETE`.

GDPR Art.17 ("right to erasure") may, on data-subject request and after legal review, oblige STOA to **erase or pseudonymize personal data** about a natural person — including data carried in audit events such as `actor_email` and free-text justifications.

These two requirements collide head-on:

- A literal `UPDATE` or `DELETE` on `audit_events` to honour an erasure request violates DORA's integrity invariant.
- A literal refusal to act on an erasure request violates GDPR.

The current code (`control-plane-api/src/services/audit_service.py:420-461`) chooses the GDPR side by executing `UPDATE audit_events SET actor_id = pseudo_id, actor_email = NULL`. This silently breaks DORA. No ADR documents the trade-off. No DPO sign-off exists in repo.

DORA reading: erasure is **not** absolute when a legal/regulatory retention obligation exists. STOA, as a regulated ICT service for financial entities under DORA, has such an obligation for audit data needed for operational resilience and incident reconstruction. The reconciliation is therefore not "always GDPR wins" but "GDPR + balancing test against DORA retention".

## 3. Problem

We must answer, in a regulator-defensible way:

1. **What** in an audit row is personal data subject to erasure?
2. **What** is regulatory data not subject to erasure during the retention window?
3. **How** do we satisfy a valid Art.17 request without mutating an append-only table?
4. **Who** can authorize an erasure operation, and **what** is logged?
5. **How long** is data kept and on what legal basis?

## 4. Decision

We adopt a **pseudonymization-by-auxiliary-table** model. The source row in `audit_events` is never mutated.

### 4.1 Data classification in audit events

Fields are classified as:

| Classification | Fields | Retention | Erasable on Art.17 |
|----------------|--------|-----------|---------------------|
| **Regulatory** | `event_id`, `created_at`, `tenant_id`, `actor_tenant_id`, `correlation_id`, `resource_type`, `resource_id`, `action`, `outcome`, `approval_reference`, `policy_version`, `row_hash` | **5 years (DORA Art.11)** | ❌ Not erasable during window |
| **Identifying / personal** | `actor_id` (when natural person), `actor_email`, `client_ip`, `user_agent`, `session_id`, `before`/`after`/`details` JSONB when they contain personal data | 5 years in pseudonymized form | ✅ Pseudonymizable on valid request |
| **Sensitive context** | `approval_justification` (free text), `before`/`after` (free shape) | 5 years; **must be reviewed** for personal content before storage | ⚠️ Case-by-case |

### 4.2 Pseudonymization mechanism

A valid Art.17 request triggers the creation of one row in a separate, restricted-access table:

```sql
CREATE TABLE pseudonymized_audit_erasures (
  erasure_id            UUID PRIMARY KEY,
  request_received_at   TIMESTAMPTZ NOT NULL,
  legal_basis           TEXT NOT NULL,          -- e.g., "GDPR Art.17(1)(a)"
  dpo_approver_id       UUID NOT NULL,
  dpo_approved_at       TIMESTAMPTZ NOT NULL,
  subject_external_ref  TEXT,                   -- opaque ref; not the email
  pseudonymization_key  BYTEA NOT NULL,         -- per-subject random salt, encrypted
  scope_actor_ids       UUID[] NOT NULL,        -- actor_ids in scope
  scope_event_ids       UUID[] NOT NULL,        -- specific events redacted
  redaction_map         JSONB NOT NULL          -- field-by-field replacement spec
);
```

Queries on `audit_events` go through a **view** `audit_events_redacted` that:

- joins with `pseudonymized_audit_erasures` on `actor_id` / `event_id`,
- replaces in-flight `actor_email` with `'pseudo:<hash>'`, `client_ip` with `0.0.0.0`, etc., according to `redaction_map`,
- leaves regulatory fields intact.

**The source `audit_events` row is never touched.** Hash chain stays valid. Integrity proof to regulator is preserved.

### 4.3 Access control

- `audit_events` raw table: only platform-internal roles (`cpi-admin`, `auditor`) with explicit grant. Reading raw is itself audited.
- `audit_events_redacted` view: default for SOC, support, tenant admins.
- `pseudonymized_audit_erasures`: write only via DPO-authenticated path. Read by DPO + Legal.

### 4.4 Workflow for an Art.17 request

```
Data subject request →
  Legal/DPO assessment (balancing test vs DORA retention obligation) →
  Decision:
    (a) reject (cite retention obligation) → response logged in pseudonymized_audit_erasures.legal_basis with "DORA Art.11 retention overrides"
    (b) full pseudonymization → row inserted in pseudonymized_audit_erasures, view begins redacting
    (c) partial pseudonymization (e.g. justification text only) → row with field-scoped redaction_map
  Confirmation sent to data subject within GDPR statutory delay.
```

### 4.5 Retention

- Audit events: **5 years** from `created_at` (DORA Art.11 minimum).
- After 5 years: scheduled bulk deletion under break-glass procedure (drop trigger inside transaction, full audit of operation including operator, batch hash, count). The deletion event is itself an audit event in the new chain.
- `pseudonymized_audit_erasures` retained **according to a DPO-approved legal basis, minimum necessary, dual-control access** (DPO + Legal jointly). The default proposed for review is "retain while the corresponding audit events still exist, plus statutory liability period". The DPO and Legal review may impose stricter or longer retention. This ADR explicitly does not adopt a "forever" default; the final value is signed off in the runbook and recorded in the §6 sign-off block.

### 4.6 What the trigger lets through

The PG trigger from ADR-070 raises on `UPDATE`/`DELETE`. Three exceptions only:

1. **Retention purge** — break-glass procedure as above. Logged.
2. **Schema migration** — alembic-managed, no row mutation, only structure. Trigger drop is per-deployment break-glass with Security sign-off.
3. **Disaster recovery restore** — temporary trigger disable during point-in-time restore from WAL. Logged in operations runbook + post-restore reconciliation.

GDPR erasure is **not** an exception. It works through the view, not through mutation.

## 5. Consequences

### Positive

- Both DORA Art.11 and GDPR Art.17 are satisfied. Defensible to either regulator.
- Erasure becomes auditable: DPO approval, legal basis, scope, and reversibility (or not) of the pseudonymization key are recorded.
- The hash chain remains valid forever.

### Negative

- Operational complexity: queries must go through the redacted view; raw-table access is an audited event.
- Storage cost: `audit_events` rows survive 5 years even for natural persons whose identifying data is redacted.
- DPO becomes a hard dependency for erasure operations. Process latency increases (acceptable: GDPR allows reasonable response time).

### Neutral

- The legal team should validate, jurisdiction-by-jurisdiction, that the chosen approach satisfies regulators. STOA operates primarily under EU jurisdictions; this ADR is written for that scope.

## 6. Implementation

**Hard-blocked until DPO sign-off and Legal review.** Code merging the alembic migration is the trip-wire.

| Deliverable | Owner | Surface |
|-------------|-------|---------|
| Alembic: create `pseudonymized_audit_erasures` + `audit_events_redacted` view | CP-API + Compliance | `control-plane-api/alembic/versions/` |
| Rewrite `erase_user_pii()` to insert into the auxiliary table, not UPDATE | CP-API | `control-plane-api/src/services/audit_service.py:420-461` |
| Route all read paths through the view | CP-API | every audit query call site |
| DPO console (read + approve erasures) | UI | `control-plane-ui/` (new screen) |
| Runbook: break-glass retention purge | Ops | `docs/runbooks/audit-retention-purge.md` (new) |
| Runbook: Art.17 request workflow | DPO + Legal | `docs/runbooks/gdpr-art17-workflow.md` (new) |

## 7. Alternatives Considered

| Option | Verdict |
|--------|---------|
| Accept current `UPDATE audit_events` behaviour | ❌ Violates DORA Art.11, breaks hash chain |
| Hard-refuse all Art.17 erasure requests citing DORA | ❌ Disproportionate; fails GDPR balancing test |
| Mutate in place but keep a "shadow" copy of original elsewhere | ❌ Two sources of truth, complex auth, no clear winner |
| Encrypt personal fields per subject and "throw away the key" on erasure | ⚠️ Cryptographic erasure works but doesn't satisfy auditors who require demonstrable retention of regulatory fields. Useful as *additional* layer for `before/after` JSONB. |
| **Pseudonymization via auxiliary table + read-time redaction view** | ✅ Selected |

## 8. References

- Audit cross-cutting "Conflit GDPR vs DORA non résolu"
- Decision record §C5 and §3.3 Q4
- ADR-070 (immutability invariant — companion)
- GDPR Regulation (EU) 2016/679 Art.5, 17, 25
- DORA Regulation (EU) 2022/2554 Art.11
- EDPB Guidelines 01/2022 on data subject rights
- ENISA "Recommendations on shaping technology according to GDPR provisions" (2018)

## 9. Open questions for sign-off

- Should the pseudonymization key be retrievable by DPO + Legal jointly (re-identification possible for valid law enforcement) or destroyed (one-way)? (Recommendation: **retrievable with dual-control**, per ENISA; not destroyed, to allow lawful disclosure.)
- Does Legal accept `redaction_map` as the canonical artefact for "what was redacted, when, by whom"? (Recommendation: yes; it is the audit trail of the audit redaction.)
- What is the SLA for responding to an Art.17 request given the DPO-in-the-loop process? (Recommendation: target 21 days, GDPR statutory limit 30 days extendable to 90.)
