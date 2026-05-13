---
title: "ADR-068: Audit Log Actor/Resource/Action Doctrine"
sidebar_label: "ADR-068: Audit Log Doctrine"
sidebar_position: 68
description: "Defines the taxonomy and invariants for STOA platform audit events: actor identification, resource taxonomy, action verbs, immutability, and integrity. Foundation for DORA Art.5/8 and NIS2 Art.21 compliance."
keywords: [ADR, audit log, DORA, NIS2, immutability, actor, resource, taxonomy, compliance]
---

# ADR-068 — Audit Log Actor/Resource/Action Doctrine

## 1. Status

**Status:** Draft

**Date:** 2026-05-13

**Deciders:** STOA Core Team (pending), Security/Compliance (pending), DPO (pending), CP-API WG (pending), Gateway WG (pending)

**Source:** `docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md` Axe C (12 binary controls) + challenger decision record §C5.

**Related decisions:** ADR-012 MCP RBAC, ADR-021 UAC-Driven Observability, ADR-054 RBAC Taxonomy v2, ADR-069 (draft, GDPR↔DORA audit reconciliation), ADR-070 (draft, Gateway Fail-Closed Posture).

## 2. Context

The 2026-05-11 audit scored audit log compliance at **3 PASS / 5 PARTIAL / 4 FAIL** against a 12-control DORA/NIS2 binary matrix. The dominant findings:

- Actor identification is partial: `actor_id`, `actor_email`, `client_ip`, `correlation_id` are present, but `session_id` is captured in OpenSearch only — not in the PostgreSQL source-of-truth.
- Resource taxonomy is present (`resource_type`, `resource_id`) but inconsistent across emitters (some emit `subscription:abc`, others emit raw UUIDs without type prefix).
- Action verbs are free-form strings, not enumerated.
- `erase_user_pii()` performs `UPDATE` statements on `audit_events`, contradicting the "append-only" comment in the model.
- Approval workflow audit lacks `approval_justification` and a structured before/after diff.
- The gateway emits to `tracing::info!` only; no inter-service chain reaches the CP audit table.

ADR-068 fixes the **schema and identity invariants**. ADR-069 handles the GDPR/DORA tension. ADR-070 handles the gateway posture. The three ADRs are a triplet.

## 3. Problem

Without a single, codified taxonomy:

- SOC queries return inconsistent shapes per emitter; forensic correlation fails.
- Regulators ask "show me every action `requester=alice@x` took on `resource_type=subscription` between dates" and receive a partial answer.
- A `UPDATE` on `audit_events` from GDPR erasure code violates DORA Art.11 (5-year integrity) silently.
- Approval audit entries cannot prove 4-eyes because acteur separation is not modelled.

## 4. Decision

We codify the **canonical audit event schema** for the STOA platform and the invariants that emitters must respect.

### 4.1 Canonical event fields (PostgreSQL `audit_events`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `event_id` | UUIDv7 | ✅ | Monotonic, time-sortable. |
| `created_at` | `timestamptz` | ✅ | UTC. Sourced from PG `clock_timestamp()`, not application clock. |
| `tenant_id` | UUID | ✅ | The tenant whose data is touched. Cross-tenant emits MUST split into two rows. |
| `actor_id` | UUID or string | ✅ | Keycloak `sub`. Use `"system:<service>"` only for non-human-triggered events (e.g., scheduled purge). |
| `actor_email` | string | ⚠️ | Required for human actors, NULL for system actors. |
| `actor_tenant_id` | UUID | ✅ | Tenant the actor belongs to; may differ from `tenant_id` (cross-tenant operation by `cpi-admin`). |
| `session_id` | string | ✅ (P1) | Keycloak session SID. Added by middleware. **New** vs current model. |
| `client_ip` | inet | ✅ | Source IP at the edge. |
| `user_agent` | string | ⚠️ | UA where applicable. |
| `correlation_id` | UUID | ✅ | End-to-end request ID. Propagated through Gateway↔CP-API via `X-Correlation-Id`. |
| `resource_type` | enum | ✅ | See §4.2. |
| `resource_id` | string | ✅ | The resource's primary key. `null` not permitted; for create-events use the post-create id. |
| `action` | enum | ✅ | See §4.3. |
| `outcome` | enum | ✅ | `success` \| `denied` \| `error` \| `pending_approval`. |
| `approval_reference` | UUID | ⚠️ | Set when `outcome=success` followed an approval step. References `approvals.id`. |
| `approval_justification` | text | ⚠️ | Required when `action ∈ {approve, revoke, escalate}` or `resource_type=destructive_tool`. |
| `policy_version` | string | ⚠️ | The policy version active at decision time. Required for gateway-emitted events. |
| `before` / `after` | JSONB | ⚠️ | Structured diff for mutations. Sanitized — no secrets, no PII beyond actor_email. |
| `details` | JSONB | ⚠️ | Free-form sanitized context. |

### 4.2 Resource taxonomy

The `resource_type` is an enum, **not** a free string. Initial set:

```
subscription, application, api, plan, contract, contract_version,
tool, mcp_tool, mcp_server, tool_permission,
user, service_account, role, role_grant, oauth_client,
tenant, environment, gateway_instance, certificate,
audit_event, approval, policy, policy_bundle,
secret_ref (no value, only ref), webhook, kafka_topic
```

Format: `resource_type:resource_id` is the canonical reference string used in logs and dashboards.

### 4.3 Action taxonomy

The `action` is an enum. Initial set, grouped:

- **Lifecycle**: `create`, `update`, `delete`, `archive`, `restore`
- **State machine**: `request`, `approve`, `reject`, `revoke`, `suspend`, `reactivate`, `expire`, `escalate`
- **Access**: `grant`, `revoke_grant`, `login`, `logout`, `token_issue`, `token_revoke`
- **Invocation**: `tool_call`, `tool_call_denied`, `api_call`, `api_call_denied`
- **Approval**: `approval_request`, `approval_granted`, `approval_denied`, `approval_token_issued`, `approval_token_used`, `approval_token_rejected`
- **System**: `purge`, `rotate`, `pseudonymize`, `migrate`, `health_degrade`, `health_restore`

### 4.4 Immutability invariant

`audit_events` is **append-only at the database level**. A PostgreSQL trigger MUST raise an exception on `UPDATE` or `DELETE`:

```sql
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only (ADR-068)';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();
```

GDPR erasure does **not** mutate this table. See ADR-069 for the pseudonymization model (auxiliary table).

Bulk retention purges run via a break-glass procedure that temporarily drops the DELETE trigger inside a transaction with full audit of the operation itself. Procedure must be documented separately and require security sign-off per execution.

### 4.5 Integrity

Each row computes a `row_hash` at insert time:

```
row_hash = sha256(
  prev_row_hash_for_this_tenant
  || event_id
  || created_at
  || tenant_id
  || actor_id
  || action
  || resource_type || ':' || resource_id
  || outcome
)
```

Per-tenant hash chain. Daily, an external WORM export signs the latest hash per tenant. Tampering becomes detectable.

**Concurrency invariant.** Two concurrent inserts on the same `tenant_id` MUST NOT read the same `prev_row_hash`. The chain head is therefore stored explicitly and serialized:

```sql
CREATE TABLE audit_chain_heads (
  tenant_id     UUID PRIMARY KEY,
  last_row_hash BYTEA NOT NULL,
  last_event_id UUID NOT NULL,
  updated_at    TIMESTAMPTZ NOT NULL
);
```

Insert path (mandatory):

1. `BEGIN`
2. `SELECT last_row_hash FROM audit_chain_heads WHERE tenant_id = $1 FOR UPDATE` — row lock per tenant; concurrent writers wait.
3. Compute `row_hash` from the locked `last_row_hash`.
4. Insert into `audit_events` with computed `row_hash`.
5. `UPDATE audit_chain_heads SET last_row_hash = ..., last_event_id = ..., updated_at = now() WHERE tenant_id = $1`.
6. `COMMIT`.

Equivalent (and acceptable) alternative for high-throughput tenants: PostgreSQL **transaction-level advisory lock** keyed on tenant id (`pg_advisory_xact_lock(hashtext($1)::bigint)`) instead of `FOR UPDATE` on the head row. The chain head is still updated in the same transaction. Either mechanism produces a strict serial order per tenant. Implementations choosing one or the other should document the choice in a follow-up note; mixing within a deployment is forbidden.

Out of scope: cross-tenant ordering. Tenants are independent chains by design.

### 4.6 Gateway → CP propagation

Gateway-emitted events use the same schema and the same `correlation_id`. Transport is the inter-service endpoint defined in the corrective plan §6.1 and to be detailed in a follow-up ADR (or ADR-070 §gateway-emit). Buffered + signed + replayed if CP transiently unreachable. **Cache-and-deny if CP is durably unreachable** (per ADR-070).

## 5. Consequences

### Positive

- DORA Art.5/8 (governance, protection) and NIS2 Art.21 (logging) become defensible with a single citeable taxonomy.
- Forensic queries become uniform; SOC tooling can rely on enums.
- Hash chain produces tamper-evidence without external WORM hardware (WORM adds optional defense-in-depth).
- Approval audit (`approval_token_issued`/`used`/`rejected`) is first-class.

### Negative

- Migration cost: existing free-form `action`/`resource_type` strings must be normalized into enums. Backfill plan needed.
- Insert latency increases by hash computation (~µs per row, negligible).
- Inter-service emit requires gateway↔CP HMAC and replay buffer — engineering work shared with ADR-070.

### Neutral

- The `details` JSONB column remains for emitter-specific context. Schema is intentionally **not** prescriptive there.

## 6. Implementation

This ADR is **non-executable until ADR-069 (GDPR↔DORA) is signed off, because the immutability invariant collides with the current `erase_user_pii()` behaviour**. The two ADRs are a coupled pair.

| Deliverable | Owner | Surface |
|-------------|-------|---------|
| Alembic migration: enum types, new columns, trigger, hash chain | CP-API | `control-plane-api/alembic/versions/` |
| Audit emitter library: enforces enum + computes hash | CP-API | `control-plane-api/src/services/audit_service.py` |
| Middleware: `session_id` and `correlation_id` propagation | CP-API | `control-plane-api/src/middleware/` |
| Gateway audit client (sender side) | Gateway | `stoa-gateway/src/audit/` (new) |
| CP-API inbound endpoint `/v1/internal/audit/emit` | CP-API | `control-plane-api/src/routers/` (new) |
| WORM export job (daily) | Platform | Helm CronJob, S3 Object Lock bucket |

## 7. Alternatives Considered

| Option | Verdict |
|--------|---------|
| Keep free-form `action` strings | ❌ Inconsistent emitters, regulator query fails |
| Enforce immutability at ORM level only (no PG trigger) | ❌ Bypassable by direct SQL / break-glass without audit trail |
| Use external WORM (S3 Object Lock) only, skip in-DB hash chain | ❌ WORM hardware/cloud lock-in; in-DB chain is portable |
| Hash chain across all tenants (single chain) | ❌ Tenant-scoped queries cannot verify integrity without scanning all rows |
| **Per-tenant hash chain + optional WORM** | ✅ Selected |

## 8. References

- Audit §C "Audit log + traçabilité DORA/NIS2" (12-control matrix)
- Decision record §C5 "Audit immutability: trigger strict, procédure migration séparée"
- ADR-069 (companion, GDPR/DORA reconciliation)
- ADR-070 (companion, gateway fail-closed + emit)
- DORA Regulation (EU) 2022/2554 Art. 5, 8, 11, 17
- NIS2 Directive (EU) 2022/2555 Art. 21
- NIST SP 800-53 SC-7 (audit integrity)

## 9. Open questions for sign-off

- Should `policy_version` be mandatory for **all** decisions, or only for gateway-emitted denies? (Recommendation: gateway denies only, to keep cost manageable.)
- Hash function: stick with SHA-256, or move to SHA-512/blake3? (Recommendation: SHA-256, broad regulator familiarity.)
- WORM bucket vendor: AWS S3 Object Lock vs OVH Cloud Archive? (Recommendation: defer to ops; both meet requirement.)
