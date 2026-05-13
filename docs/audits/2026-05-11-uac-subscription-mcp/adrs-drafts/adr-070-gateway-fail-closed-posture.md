---
title: "ADR-070: Gateway Fail-Closed Posture"
sidebar_label: "ADR-070: Gateway Fail-Closed"
sidebar_position: 70
description: "Codifies the fail-closed defaults for stoa-gateway: deny on Control Plane unreachable, deny on policy load failure, deny on expired cache, no implicit read-only fallback, readiness probe reflects true enforcement state."
keywords: [ADR, gateway, fail-closed, DORA, NIS2, resilience, policy, RBAC, cache]
---

# ADR-070 — Gateway Fail-Closed Posture

## 1. Status

**Status:** Draft

**Date:** 2026-05-13

**Deciders:** STOA Core Team (pending), Security/Compliance (pending), **Business owner (pending — fail-closed has product impact)**, Gateway WG (pending), Platform Ops (pending).

**Source:** `docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md` Axe D (findings GW-1 through GW-9) + challenger decision record §C2 + §C3 + §3.3 Q1 + Q2.

**Related decisions:** ADR-035 Gateway Adapter Pattern, ADR-037 Deployment Modes (Sovereign First), ADR-044 MCP OAuth Gateway Proxy, ADR-066 UAC as LLM-Optimized Executable Contract, ADR-067 (draft, UAC Doctrine), ADR-068 (draft, Audit Log Doctrine).

## 2. Context

The audit identifies **five permissive fallback paths** in `stoa-gateway`:

1. **Control Plane unreachable** → `tool_permissions.rs:88-96` defaults all permissions to allow.
2. **Policy engine load failure** → `state.rs:176-189` creates a disabled engine (`enabled=false`) that allows everything.
3. **Classification VH soft-mode** → `proxy/dynamic.rs:410-422` logs decision but does not deny.
4. **`requires_human_approval=true`** → never checked at runtime (cross-ref: ADR-067).
5. **Deprovision one-shot** → revoked subscriptions can still be served if gateway was offline at revoke time.

Combined, these turn the gateway into a **fail-open** component when its dependencies degrade. For a STOA tenant under DORA/NIS2, this is a regulatory NOGO.

The challenger's verdict (§C2, §C3, §3.3 Q1-Q2) makes fail-closed mandatory but acknowledges product impact: CP-API outages will materialize as access incidents on the data plane. That must be a **signed business decision**, not a quietly-shipped technical default.

## 3. Problem

We need explicit, signed answers to:

1. When the gateway loses its source of truth (CP-API), what behaviour MUST it exhibit?
2. How fresh must a cached policy be before it can be trusted?
3. Is a "degraded read-only" mode acceptable?
4. What does `readiness` actually mean?
5. How is the operator notified, and what is the runbook?

## 4. Decision

The gateway adopts **deny-by-default** as its first-order posture. All exceptions are explicit, scoped, signed, and audited.

### 4.1 Fail-closed invariants

| Condition | Behaviour |
|-----------|-----------|
| CP-API unreachable AND no fresh signed cache | **Deny new calls.** Return 503 with `Retry-After` and a stable error code. Existing in-flight calls drain (no abrupt cut). |
| CP-API unreachable AND fresh signed cache exists | **Allow per cache, only within cache validity.** Cache expiration is **not** extensible locally. |
| Policy bundle load fails at boot | **Boot fails.** Readiness FAIL. Process exits non-zero. |
| Policy bundle reload (SIGHUP) fails | **Keep previous bundle in force.** Emit alert. Subsequent SIGHUP retries. No silent transition to permissive. |
| Permission for a (tenant, tool) absent from cache | **Deny.** Emit `tool_call_denied` with `reason="permission_absent_in_cache"`. |
| Revocation event for (tenant, subscription) received | **Invalidate immediately**, even if cache has not expired. Revocation has priority over cache. |
| `requires_human_approval=true` on tool with no valid approval token | **Deny.** Emit `approval_required`. (Cross-ref: ADR-067, plan §C4.) |
| `inputSchema` validation fails | **Deny.** No tool invocation. |
| `outputSchema` validation fails | **Strip / replace response with error** (do not return malformed contract). |

### 4.2 Signed cache artefact

The challenger (§C3) requires the cache, when used during outage, to be a **first-class artefact**, not an in-memory shortcut. Specification:

```yaml
policy_cache_artefact:
  policy_version: "v2026-05-13-1430"
  issued_at: "2026-05-13T14:30:00Z"
  expires_at: "2026-05-13T15:30:00Z"      # max 60 min, configurable, NEVER extended locally
  tenant_scope: "tenant-abc"
  signature: "ed25519:<hex>"               # signed by CP-API issuance key
  signing_key_id: "cp-api-pk-2026-05"
  allow_set:
    tools:
      - tool_name: "customer_get_customer"
        side_effects: read
        requires_human_approval: false
    subscriptions:
      - subscription_id: "sub-xyz"
        api_id: "api-foo"
        plan_id: "free"
  deny_default: true                       # permission absent → deny
```

The cache is verified on every consult. A stale or tampered cache is treated as "no cache".

### 4.3 No implicit read-only fallback

The challenger (§3.3 Q1) explicitly forbids an implicit read-only degradation. STOA does not have, at this stage, a machine-readable proof per-operation that the operation is non-mutating (the UAC `side_effects` field is moving toward that state but is not universally typed yet — see ADR-067).

Until ADR-067 (a) ships typed `side_effects` in `ToolDefinition` and (b) is itself signed off as the source of truth, a "read-only mode" does not exist. Any future read-only mode will require its own ADR amendment to this one.

### 4.4 Readiness vs liveness

| Probe | Meaning | Conditions for OK |
|-------|---------|-------------------|
| **Liveness** | Process is up | Gateway process is responsive (does not deadlock) |
| **Readiness** | Gateway can faithfully enforce policy | (a) Policy bundle loaded and valid; (b) Either CP-API reachable in last `cache_validity` window OR signed cache valid; (c) Audit emit buffer below high-water mark |

Failing readiness causes the orchestrator (K8s) to **stop routing new traffic** while existing traffic drains. Liveness is **not** failed in this case — the process is healthy, it is just refusing to operate beyond its safety envelope.

### 4.5 Observability and alerting

Every fail-closed transition emits:

- A structured audit event (`action=health_degrade`, `reason=...`, `policy_version`).
- A Prometheus metric `stoa_gateway_failclosed_active{reason="cp_unreachable"}` set to 1.
- An OTLP span on the transition.

An alert MUST fire when `stoa_gateway_failclosed_active{} > 0` for more than 60 seconds.

### 4.6 Gateway → CP-API audit emit (Phase 0 minimum)

Per the challenger's §C1 Option A (recommended), a minimal version of the audit chain is **promoted to Phase 0** of the corrective plan. Scope of the minimal version:

- Endpoint `/v1/internal/audit/emit` on CP-API (HMAC-signed inter-service auth).
- Gateway audit client buffering only **denies** and **approval-gated** events at first (not every successful call — that's Phase 1).
- Same schema as ADR-068.

**Buffer durability and overflow semantics (challenger condition C1 reinforced).** A simple in-memory buffer with drop-on-overflow would re-introduce silent audit gaps and is **forbidden** for the critical events in scope (denies, approval-gated, health-degrade). The following semantics are mandatory:

1. **Durable local spool.** The buffer is backed by an on-disk WAL (e.g., a bounded directory with rotated append-only segments). A process restart preserves unflushed events.
2. **Bounded growth with readiness coupling.** A high-water mark is configurable (default: 80% of the spool capacity). Crossing it MUST flip the gateway's readiness probe to FAIL — orchestrator stops routing new traffic until the buffer drains. Liveness is not affected.
3. **No silent drop.** If the spool genuinely cannot accept (disk full, corruption), the gateway emits a synchronous `audit_gap_declared` event locally (and to stderr / orchestrator alerts) **and** transitions to fail-closed for all in-scope decisions, deny-by-default. A declared gap is an incident, not a metric line.
4. **Replay on recovery.** When CP-API becomes reachable again, the gateway drains the spool oldest-first, respecting the ADR-068 hash chain and `correlation_id` ordering. A successful drain emits `audit_chain_resumed` with the count and time window covered.
5. **Operator observability.** Spool depth, age of oldest entry, and the count of `audit_gap_declared` events are exposed as Prometheus metrics with alert thresholds.

Phase 1 expands buffering to all events. Phase 0 only carries the critical subset, but with the full durable semantics above — that is the irreducible minimum for "audit chain operational" in the challenger sense.

Without this Phase 0 minimum, the global NOGO is not lifted at Phase 0 close (per challenger §C1).

## 5. Consequences

### Positive

- A regulator query "what does the gateway do when CP is down?" has a single, citeable answer.
- DORA Art.5 (governance) and Art.9 (detection) are satisfied: degraded state is detectable, alertable, runbook-driven.
- The audit chain becomes inter-service from Phase 0 for the critical events.

### Negative

- **Product impact**: a CP-API outage now turns into a gateway access outage. Must be communicated to tenants and stakeholders; SLO must reflect that the two systems are now coupled for availability.
- Operational burden: readiness gates require operations to monitor a richer signal set.
- Latency: every cache consult verifies a signature (~µs, negligible) but adds an issuance dependency on CP-API.

### Neutral

- The "ungoverned read-only fallback" door remains closed by this ADR; any future open of that door is a new ADR with explicit consent and proof.

## 6. Implementation

This ADR is **non-executable until business sign-off** (the SLO change is not a purely technical decision) AND ADR-067/068/069 reach at least Proposed status (since fail-closed depends on typed metadata and audit chain).

| Deliverable | Owner | Surface |
|-------------|-------|---------|
| Replace `unwrap_or(&true)` with deny + circuit-breaker | Gateway | `stoa-gateway/src/control_plane/tool_permissions.rs:88-96` |
| Replace permissive policy fallback with boot-fail | Gateway | `stoa-gateway/src/state.rs:176-189` |
| Implement readiness with policy + CP + buffer checks | Gateway | `stoa-gateway/src/handlers/admin/health.rs` |
| Signed cache artefact: signer in CP-API, verifier in gateway | CP-API + Gateway | new modules |
| Audit emit client (minimal: denies + approval) | Gateway | `stoa-gateway/src/audit/` (new) |
| Inbound endpoint `/v1/internal/audit/emit` | CP-API | `control-plane-api/src/routers/` (new) |
| Runbook for CP outage on gateway side | Ops + SRE | `docs/runbooks/gateway-fail-closed.md` (new) |
| Tenant SLO communication template | Product + DocOps | `docs/playbooks/cp-outage-tenant-comm.md` (new) |

## 7. Alternatives Considered

| Option | Verdict |
|--------|---------|
| Keep permissive fallbacks; document them | ❌ Manufactures paper compliance |
| Allow stale cache indefinitely during outage | ❌ Drift in policy + invisibility of revocations |
| Implement implicit read-only fallback today | ❌ No machine-readable proof of "read-only" yet (see ADR-067) |
| Make CP-API a hard dependency at gateway startup | ❌ Boot couples too tightly; cache-on-boot mitigation is enough |
| **Deny-by-default + signed cache + readiness gate + Phase 0 audit chain** | ✅ Selected |

## 8. References

- Audit Axe D (GW-1 through GW-9)
- Decision record §C2, §C3, §3.3 Q1, §3.3 Q2, §C1 (Option A recommendation)
- ADR-067 (UAC doctrine — companion)
- ADR-068 (audit log doctrine — companion)
- ADR-069 (GDPR/DORA reconciliation — companion)
- DORA Regulation (EU) 2022/2554 Art. 5, 8, 9, 17
- NIS2 Directive (EU) 2022/2555 Art. 21
- NIST SP 800-160 (resilient systems)

## 9. Open questions for sign-off

- Max cache TTL during outage: 60 minutes (proposed) is a balance between availability and policy freshness. Business may prefer 30 minutes (stricter) or 120 minutes (more available). Need explicit value.
- Should denied calls emit `Retry-After: <seconds>` or just 503? (Recommendation: `Retry-After` with jitter, to avoid stampede on CP recovery.)
- Should the gateway expose a tenant-visible status endpoint `/status` showing "degraded — fail-closed since X"? (Recommendation: yes, alleviates support load during outage.)
