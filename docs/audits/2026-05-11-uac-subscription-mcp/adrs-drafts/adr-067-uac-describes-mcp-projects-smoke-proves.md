---
title: "ADR-067: UAC Describes / MCP Projects / Smoke Proves"
sidebar_label: "ADR-067: UAC Doctrine"
sidebar_position: 67
description: "Formalizes the canonical doctrine that UAC is the primary product contract, MCP tools are projections of UAC operations, and smoke tests are the runtime proof of projection."
keywords: [ADR, UAC, MCP, doctrine, projection, smoke tests, runtime enforcement]
---

# ADR-067 — UAC Describes / MCP Projects / Smoke Proves

## 1. Status

**Status:** Draft

**Date:** 2026-05-13

**Deciders:** STOA Core Team (pending), Security/Compliance (pending), Gateway WG (pending), CP-API WG (pending)

**Source:** `docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md` (MCP-1, MCP-2, MCP-3) + `docs/plans/2026-05-11-uac-subscription-mcp-corrective.md` §4.2 + challenger decision record §3.3 (C4).

**Related decisions:** ADR-006 Tool Registry Architecture, ADR-012 MCP RBAC Architecture, ADR-021 UAC-Driven Observability, ADR-045 stoa.yaml Declarative Spec, ADR-051 Lazy MCP Discovery, ADR-066 UAC as LLM-Optimized Executable Contract.

**Supersedes / amends:** none. Codifies a doctrine previously living only in `.claude/docs/uac-llm-ready.md`.

## 2. Context

A doctrinal sentence has been repeatedly cited across CLAUDE.md, audit pipelines, and PR reviews:

> **UAC describes. MCP projects. Smoke proves.**

That doctrine has never been formalized in stoa-docs. It exists today in `.claude/docs/uac-llm-ready.md` and in the implicit behaviour of `UacToolGenerator` and `uac_validator`. The 2026-05-11 audit found three concrete consequences of this absence:

1. The validator enforces `side_effects=destructive ⇒ requires_human_approval=true` at **parsing** of the UAC contract, but the gateway **ignores** the flag at runtime (`stoa-gateway/src/mcp/handlers.rs:354-390`).
2. LLM metadata is projected into the MCP tool **description text only**, not into structured `ToolDefinition` fields (`stoa-gateway/src/mcp/tools/mod.rs:140-152`).
3. No smoke test proves that `tools/list` exposes the expected `tool_name` or that annotations match `side_effects`.

The doctrine must therefore be (a) elevated to ADR status, (b) made enforceable at runtime, and (c) proven by smoke tests.

## 3. Problem

A doctrine that is declared but not enforced creates regulatory and product risk:

- A regulator asking "where is destructive-operation approval enforced?" receives "in the UAC validator at parse time" — which is not where attackers or autonomous agents operate.
- An AI agent reading the tool description sees "DESTRUCTIVE — requires approval" but the gateway executes the call anyway.
- Smoke tests cover happy paths but not the contract↔projection invariant, so projection drift is invisible until a customer notices.

Codifying the doctrine without enforcement is worse than silence: it manufactures a paper compliance posture.

## 4. Decision

We adopt the canonical three-line doctrine as ADR:

```text
UAC describes.
MCP projects.
Smoke proves.
```

Concretely:

### 4.1 UAC describes

- UAC is the **primary product contract**. Any operation exposed to a consumer (API, MCP tool, future protocols) must be attached to a UAC operation or flow contract.
- Endpoint-level `llm` metadata (per ADR-066) is the **operational intent layer**.
- The hard rule is binding at all layers: `side_effects=destructive ⇒ requires_human_approval=true`. Malformed metadata is an error.

### 4.2 MCP projects

- MCP tools are **projections** of UAC operations, not first-class artefacts.
- The projection MUST carry typed metadata (not only description text):
  - `side_effects ∈ {none, read, write, destructive}` as a typed field on the wire format
  - `requires_human_approval: bool` typed
  - `safe_for_agents: bool` typed
  - `tool_name` derived deterministically from `{tenant}:{contract}:{operation_id}`
- The gateway runtime MUST read the typed fields and:
  - refuse `tools/call` when `requires_human_approval=true` and no valid approval token is presented (cross-reference: ADR-070 fail-closed posture).
  - validate inputs against the UAC `inputSchema` before invocation; validate outputs before returning.

### 4.4 Approval token invariants (binding doctrine for §4.2)

The approval token is the runtime artefact that proves a human approval has occurred and binds it to the exact intended call. **The following invariants are mandatory doctrine** (challenger condition C4); the corrective plan derives implementation from them, not the other way around.

Token format: JWT signed by CP-API, single-use. Required claims:

| Claim | Purpose |
|-------|---------|
| `jti` | Unique token id; consumed in an **atomic, durable** single-use store (gateway-side or CP-side, but atomic across replicas). |
| `tool_call_id` | The intended call's identifier; correlates to `audit_events.correlation_id`. |
| `tenant_id` | Tenant scope; the token is bound to one tenant. |
| `tool_name` | The exact MCP tool name; cross-tenant or cross-tool reuse is rejected. |
| `arguments_hash` | SHA-256 of the canonicalized JSON of the tool call arguments; **rejects intent-bound reuse**, e.g. a token approved for `delete(id=A)` cannot serve `delete(id=B)`. |
| `policy_version` | Active policy version at approval time; must match the gateway's active policy at execution time, otherwise reject. |
| `contract_version` | Active UAC contract version at approval time. |
| `requester_actor_id` | The actor requesting the call. |
| `approver_actor_id` | The actor who approved. |
| `exp` | Short TTL (recommended ≤ 5 minutes). |
| `iat`, `nbf` | Standard time bounds. |

Mandatory verification at the gateway:

1. Signature verification against CP-API public key.
2. `jti` not yet consumed; atomic CAS-style insert into the single-use store; on conflict → reject `APPROVAL_TOKEN_REPLAY`.
3. `tenant_id`, `tool_name`, `policy_version`, `contract_version` match the active call context.
4. `arguments_hash` matches the SHA-256 of the call's canonicalized arguments.
5. For operations marked 4-eyes (typically `side_effects=destructive`): `approver_actor_id != requester_actor_id` AND approver holds the required role for the operation (validated either at issuance by CP-API and trusted, or rechecked at the gateway).
6. `exp`, `nbf` within bounds.

Mandatory audit emissions:

- `APPROVAL_TOKEN_ISSUED` at issuance (CP-API), carrying `jti`, `requester_actor_id`, `approver_actor_id`, `tool_call_id`, hashed argument hash.
- `APPROVAL_TOKEN_USED` at successful consumption (gateway).
- `APPROVAL_TOKEN_REJECTED` with `reason ∈ {signature, replay, scope_mismatch, arguments_mismatch, policy_version_mismatch, 4_eyes_violation, expired, ...}`.

Without any of these invariants, the token does not prove what the doctrine requires. Implementations that omit `arguments_hash`, `jti` atomic single-use, or 4-eyes acteur separation are non-compliant with ADR-067 even if a JWT is technically present.

### 4.3 Smoke proves

- Each tenant's UAC publish flow MUST include a smoke gate that asserts:
  1. The expected `tool_name` appears in `/mcp/tools/list`.
  2. The `description` reflects `llm.summary`/`llm.intent` when metadata is present.
  3. Typed annotations on the wire match `side_effects` declared in UAC.
  4. The example input validates against `input_schema`.
  5. Read-only safe examples execute deterministically.
  6. Destructive examples are **gated** — they expose the approval requirement, they do not blindly execute.
- Smoke failure blocks publish/promote. There is no soft-mode for the projection invariant.

## 5. Consequences

### Positive

- The doctrine becomes auditable end-to-end (UAC → DB → gateway runtime → smoke).
- Regulators receive a single, citeable contract for "destructive operation governance".
- Drift between declared and projected metadata is caught at smoke time, not in incident response.

### Negative

- Backward compatibility cost: existing tenants with UAC contracts missing `endpoint.llm` get warnings; new MCP-exposed endpoints will require completed metadata before merge (V2 target per ADR-066).
- Wire format change to MCP `ToolDefinition` requires gateway version bump and client SDK alignment.
- Smoke gates add latency to publish pipelines (~minutes).

### Neutral

- ADR-066 remains the authoritative spec for *which* fields exist. ADR-067 is the *enforcement* doctrine on top.

## 6. Implementation

This ADR is **non-executable until challenger conditions C1, C2, C4 are signed off** (cf. `docs/decisions/2026-05-11-uac-subscription-mcp-corrective.md`).

Once signed:

| Deliverable | Owner | Surface |
|-------------|-------|---------|
| Typed `side_effects` field in `ToolDefinition` (Rust wire format) | Gateway | `stoa-gateway/src/mcp/tools/mod.rs` |
| Runtime read of `requires_human_approval` in `mcp_tools_call_inner` | Gateway | `stoa-gateway/src/mcp/handlers.rs:354-390` |
| Persist `endpoint.llm` JSON in `McpGeneratedTool.attributes` | CP-API | `control-plane-api/src/services/uac_tool_generator.py` |
| Smoke gate in CI publish pipeline | CI + CP-API | `.github/workflows/uac-smoke.yml` (new) |
| Input/output schema validation runtime | Gateway | `stoa-gateway/src/mcp/handlers.rs` |

## 7. Alternatives Considered

| Option | Verdict |
|--------|---------|
| Leave doctrine in `.claude/docs/` | ❌ Not citeable by regulators, drifts silently |
| Embed doctrine in ADR-066 amendment | ❌ Conflates "what fields exist" with "how they are enforced" |
| Codify only the typed wire format, skip the smoke gate | ❌ Drift invisible until prod incident |
| **Standalone ADR-067 with three pillars** | ✅ Selected |

## 8. References

- Audit findings: MCP-1 (`requires_human_approval` ignored runtime), MCP-2 (metadata not typed in tools/list), MCP-3 (annotations decorrelated from contract)
- Plan §4.2 "Doctrine exécutée au runtime"
- Decision record §C4 (approval-token enrichment) and §3.3 (4-eyes proof)
- `.claude/docs/uac-llm-ready.md` (canonical source of doctrine text, to be archived as historical)
- ADR-066 (field definitions) — predecessor

## 9. Open questions for sign-off

- Should `safe_for_agents=false` block all autonomous agents at the gateway, or only emit a warning that the client SDK can choose to honour? (Recommendation: **block** to align with fail-closed posture ADR-070.)
- Should the smoke gate run on every PR touching the tenant's UAC, or on every publish? (Recommendation: **every publish**, plus optional PR-level dry-run.)
