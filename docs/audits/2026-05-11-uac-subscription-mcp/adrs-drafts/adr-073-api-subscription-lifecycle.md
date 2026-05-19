---
title: "ADR-073: API Subscription Lifecycle"
sidebar_label: "ADR-073: Subscription Lifecycle"
sidebar_position: 73
description: "Formalizes the state machine, RBAC boundaries, and propagation contract of API subscriptions on STOA, extending ADR-001 for the consumer-producer relationship and providing the auditable workflow required by DORA/NIS2."
keywords: [ADR, subscription, lifecycle, state machine, RBAC, propagation, DORA, NIS2]
---

# ADR-073 — API Subscription Lifecycle

## 1. Status

**Status:** Draft (operator-approved 2026-05-13 — see `docs/decisions/2026-05-13-cab-2225-2229-operator-approvals.md` §CAB-2228 for conditions). Parameters fixed: `PARTIALLY_PROVISIONED` = **consumer-visible with target-level breakdown**, 4-eyes for destructive endpoints = **strict 2 distinct tenant-admins** (devops pairing NOT accepted), provisioning time budget = **15 min**. Will be promoted to `Proposed` then `Accepted` in `stoa-docs/` after CAB-2229 closes.

**Date:** 2026-05-13

**Deciders:** Operator (founder, acting as product / security / privacy / business decision owner — solo project mode; no separate Product / Security / Gateway role exists at this stage).

**Source:** `docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md` Axe A (findings SUB-1 through SUB-7) + challenger decision record §C6.

**Extends:** ADR-001 Third-Party API Exposure Strategy (Control Plane / Data Plane separation). ADR-001 defines the architecture; ADR-073 defines the lifecycle inside it.

**Related decisions:** ADR-022 UAC Tenant Architecture, ADR-054 RBAC Taxonomy v2, ADR-055 Portal/Console Governance, ADR-067 UAC as Executable Contract, ADR-069 UAC Doctrine, ADR-070 Audit Log Doctrine, ADR-072 Gateway Fail-Closed Posture.

## 2. Context

A consumer tenant subscribes to a producer tenant's API on STOA. The current implementation is **functional for the happy path** but exhibits several lifecycle gaps that prevent regulatory acceptance:

- **Dual state fields**: `status` and `provisioning_status` track lifecycle in parallel, with no formal mapping. A subscription can be `status=ACTIVE` and `provisioning_status=PROVISIONING` simultaneously, which means the consumer-visible state is misleading.
- **No DEPROVISIONING state**: a revocation immediately flips `status=REVOKED` while the deprovision request to the gateway is in flight. If the gateway is unreachable, the route remains live indefinitely (SUB-1, P0).
- **No multi-target reconciliation**: in multi-gateway or multi-region deployments, partial provisioning is invisible (challenger §C6).
- **TTL extension lacks commit** (SUB-2, P0).
- **Cross-tenant subscription not validated** at create time (SUB-6).
- **Approval not formally a state**: PENDING jumps to ACTIVE directly on auto-approve or manual approve, with no observable APPROVED-but-not-PROVISIONED moment.

ADR-001 told us **how** STOA is architected. ADR-073 tells us **how a subscription lives, ages, and dies** inside that architecture.

## 3. Problem

A subscription lifecycle is the unit observed by regulators: who requested, who approved, what was granted, when did it become effective on the data plane, when was it revoked, when was the revocation effective on the data plane.

Without a formalized state machine:

- DORA Art.5 (governance / accountability) cannot be cleanly demonstrated.
- DORA Art.17 (incident reporting ≤72h) cannot rely on a consistent observable subscription state for forensic timeline reconstruction.
- NIS2 Art.21 (technical measures) cannot prove revocation latency or partial-failure handling.
- Product UI cannot show consumers an honest state.

## 4. Decision

We adopt a **single unified state machine** for subscription lifecycle, with **per-target acknowledgement** for multi-gateway deployments, and **explicit audit emission** at every transition.

### 4.1 Unified state machine

```
                    ┌────────────────────────────────────────────────┐
                    │                                                │
   POST /subs       │                                                │
       ▼            ▼                                                │
   REQUESTED ──→ PENDING ──── reject ──→ REJECTED                    │
                    │                                                │
              approve (manual)                                       │
                    │       ┌─── auto_approve (plan rule)            │
                    ▼       ▼                                        │
                 APPROVED                                            │
                    │                                                │
                    ▼                                                │
             PROVISIONING ──── any target fails after retries ──→ PROVISIONING_FAILED
                    │                                                │
       all required targets ack                                      │
                    │                                                │
                    ├── some targets ack, some not ───→ PARTIALLY_PROVISIONED
                    │                                                │
                    ▼                                                │
                  ACTIVE ◄──── reactivate ──── SUSPENDED ◄── suspend ┘
                    │
              revoke│ ──── (or TTL expiry)
                    ▼
                REVOKING
                    │
                    ▼
             DEPROVISIONING ──── any target fails after retries ──→ DEPROVISIONING_FAILED
                    │
       all required targets ack revocation
                    │
                    ▼
                 REVOKED
```

### 4.2 State invariants

| State | Consumer-facing meaning | Gateway behaviour |
|-------|--------------------------|-------------------|
| `REQUESTED` | Submitted, not yet visible to producer | No gateway entry |
| `PENDING` | Awaiting producer approval | No gateway entry |
| `REJECTED` | Producer refused | No gateway entry |
| `APPROVED` | Producer accepted, not yet usable | No gateway entry yet |
| `PROVISIONING` | Being installed on data plane | Targets being notified |
| `PARTIALLY_PROVISIONED` | Some targets ack, others not | Allowed only on ack'd targets |
| `PROVISIONING_FAILED` | Retries exhausted | No allow anywhere |
| `ACTIVE` | Fully usable | All targets allow |
| `SUSPENDED` | Temporary hold by producer or system | Deny everywhere (gateway invalidates immediately, per ADR-072) |
| `REVOKING` | Revoke initiated, deprovision in flight | Deny new calls, drain in-flight |
| `DEPROVISIONING` | Targets being notified to remove | Same as REVOKING |
| `DEPROVISIONING_FAILED` | Retries exhausted; **alertable** | Deny enforced at gateway via ADR-072 cache invalidation; ops manual intervention |
| `REVOKED` | Final; immutable | No allow anywhere |

`ACTIVE` is reached **only if all required targets ack the provisioning**. `REVOKED` is reached **only if all required targets ack the revocation OR a higher-level deny mechanism guarantees no service** (e.g., the ADR-072 cache invalidation already prevents allow regardless of target ack).

**Default doctrine on `required` flag.** In standard STOA deployments — a tenant served by one or more gateways behind a single Control Plane — every gateway reachable for that tenant is `required=true`. `PARTIALLY_PROVISIONED` is therefore an **operator-visible degradation state**, not a normal usage state: it means some gateways are out of sync with the policy intent and the situation must be reconciled. Consumer surface MAY display it (recommendation §9) but consumers should treat it as "temporary degraded availability", not as "feature partially enabled".

The `required=false` value is reserved for explicit, advanced topologies: shadow/canary gateway, observability-only data plane, soft-launch region. Setting `required=false` requires an out-of-band justification recorded on the `subscription_target` row (`details.justification`) and is itself an audited event. The default for any new target is `required=true`.

A subscription is "usable" iff `status=ACTIVE` AND every `required=true` target has `provisioned_at IS NOT NULL` AND no `required=true` target is in revocation/deprovisioning. No other combination is considered usable; the gateway-side cache invalidation (ADR-072) is the final fail-safe regardless of the field.

### 4.3 Per-target ack model

Each subscription has a `targets` collection:

```sql
CREATE TABLE subscription_targets (
  subscription_id    UUID NOT NULL REFERENCES subscriptions(id),
  target_kind        TEXT NOT NULL,         -- 'gateway', 'webMethods', 'kong', ...
  target_id          TEXT NOT NULL,
  required           BOOLEAN NOT NULL,      -- failing a required target blocks ACTIVE
  provisioned_at     TIMESTAMPTZ,
  deprovisioned_at   TIMESTAMPTZ,
  last_error         TEXT,
  retry_count        INT NOT NULL DEFAULT 0,
  PRIMARY KEY (subscription_id, target_kind, target_id)
);
```

Per-target ack is computed asynchronously via the gateway → CP audit emit chain (ADR-072 §4.6, promoted to Phase 0).

### 4.4 RBAC matrix

| Action | Who | Notes |
|--------|-----|-------|
| `subscription:request` | `tenant-admin`, `devops` of the **consumer** tenant | |
| `subscription:approve` | `tenant-admin` of the **producer** tenant (or `cpi-admin`) | If the api has any `destructive` endpoint per ADR-069, requires **4-eyes**: two distinct producer-tenant approvers |
| `subscription:reject` | `tenant-admin` of producer | |
| `subscription:suspend` | `tenant-admin` of producer; `cpi-admin` | |
| `subscription:reactivate` | `tenant-admin` of producer; `cpi-admin` | Emits webhook (closes the audit gap SUB-3) |
| `subscription:revoke` | `tenant-admin` of consumer OR producer; `cpi-admin` | |
| `subscription:ttl_extend` | `tenant-admin` of consumer (within plan rules); producer can deny | Commit transaction explicitly (closes SUB-2) |

At creation time, the CP-API **must validate** `request.tenant_id` matches the consumer tenant inferred from caller identity AND the resolved `api.owner.tenant_id` ≠ caller tenant (closes SUB-6 for cross-tenant boundary). Same-tenant subscriptions (a tenant subscribing to its own API for testing) are allowed when explicitly flagged.

### 4.5 Audit emission

Every state transition emits one `audit_events` row using the ADR-070 schema:

- `resource_type=subscription`, `resource_id=<sub-id>`
- `action ∈ {request, approve, reject, suspend, reactivate, revoke, expire, escalate, ...}`
- `actor_id`, `actor_tenant_id`, `session_id` (per ADR-070)
- `before`/`after` carrying the state field diff
- `approval_justification` mandatory on `approve`, `reject`, `revoke`, `suspend`

Per-target ack updates emit `audit_events` of `resource_type=subscription_target` with `action ∈ {target_provisioned, target_deprovisioned, target_failed}`.

### 4.6 Idempotency and retry

- `provision_on_approval` and `deprovision_on_revocation` MUST be idempotent (closes SUB-7).
- Both MUST use a persistent retry queue with exponential backoff, max retries configurable per target, and alert on exhaustion (closes SUB-1, P0).
- A subscription remains in `*ING` state until terminal ack or retry exhaustion. The state is observable in the UI.

### 4.7 TTL extension

- Extension writes go through an explicit `commit()`, not `flush()` (closes SUB-2, P0).
- TTL extensions during a CP-API outage are **refused** by ADR-072's fail-closed posture (no local extension of cache).
- Each extension emits one audit event with the diff (`before.expires_at`, `after.expires_at`, `extend_days`).

## 5. Consequences

### Positive

- DORA Art.5/17 timeline reconstruction becomes deterministic.
- Consumer UI can show an honest state (`ACTIVE` truly means "usable on the data plane").
- Multi-gateway deployments handle partial provisioning gracefully.
- Revocation latency is measurable: `audit_events.action=revoke` to last `target_deprovisioned` defines the SLO.

### Negative

- Migration is sizeable: existing subscriptions need state mapping (`status=ACTIVE` + `provisioning_status=READY` → `ACTIVE`; `provisioning_status=PROVISIONING` → `PROVISIONING`; etc.). UI must follow.
- Per-target tracking adds a table and async reconciliation logic.
- 4-eyes approval for destructive-endpoint APIs increases time-to-first-call for some subscriptions; product impact must be communicated.

### Neutral

- TTL semantics, plan model, and pricing are out of scope for this ADR.

## 6. Implementation

This ADR is **non-executable until ADR-069 (typed metadata) and ADR-072 (cache + audit chain) reach Proposed**, because 4-eyes/destructive routing and target ack rely on them.

| Deliverable | Owner | Surface |
|-------------|-------|---------|
| Alembic: unify `status`, add `subscription_targets`, add transition constraints | CP-API | `control-plane-api/alembic/versions/` |
| State machine engine + transition guards | CP-API | `control-plane-api/src/services/subscription_lifecycle.py` (new) |
| Retry/idempotency for provision/deprovision | CP-API | `control-plane-api/src/services/provisioning_service.py` |
| Target ack handler (consumes gateway audit emit chain) | CP-API | new |
| 4-eyes approval for destructive-endpoint APIs | CP-API + UI | new |
| TTL extension commit + tests | CP-API | `control-plane-api/src/routers/subscriptions.py:562` |
| UI: state machine reflection, target-level status | Console UI | `control-plane-ui/` |
| BDD smoke: revoke ≤ 5 min latency under load | E2E | `e2e/features/subscription-lifecycle.feature` (new) |

## 7. Alternatives Considered

| Option | Verdict |
|--------|---------|
| Keep dual `status`/`provisioning_status` fields; document mapping | ❌ UI lies; regulators see ambiguity |
| Add states only to `provisioning_status`; leave `status` simple | ❌ Confuses what is "live" |
| Per-target tracking but no `PARTIALLY_PROVISIONED` state | ❌ Half-states invisible to ops and consumers |
| Drop 4-eyes; rely on ADR-069 approval token only | ❌ Approval token proves intent binding, 4-eyes proves separation of duties — both needed for destructive endpoints |
| **Unified state machine + per-target ack + 4-eyes for destructive** | ✅ Selected |

## 8. References

- Audit Axe A (SUB-1 through SUB-7) + state-machine current vs ideal diagram
- Decision record §C6 (partial provisioning + failure states)
- ADR-001 (architecture predecessor)
- ADR-069 (destructive routing — companion)
- ADR-070 (audit emission schema — companion)
- ADR-072 (cache invalidation + audit chain — companion)
- DORA Regulation (EU) 2022/2554 Art. 5, 17
- NIS2 Directive (EU) 2022/2555 Art. 21

## 9. Open questions for sign-off

- Should `PARTIALLY_PROVISIONED` be consumer-visible or only operator-visible? (Recommendation: consumer-visible with target breakdown, to prevent support escalations.)
- Time budget before `PROVISIONING` retries exhaust into `PROVISIONING_FAILED`: default 15 minutes acceptable? (Recommendation: yes, configurable per tenant.)
- For 4-eyes: do the two approvers both need to be `tenant-admin` of the producer, or is one `tenant-admin` + one `devops` acceptable? (Recommendation: both `tenant-admin`, to keep "separation of duties" meaningful.)
