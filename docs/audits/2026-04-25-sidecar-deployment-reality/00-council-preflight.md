# CAB-2173 Council Preflight

Date: 2026-04-25
Ticket: CAB-2173
Scope: make STOA sidecar deployment real for third-party gateways and micro-gateway/mesh modes.

## Context Compiler

Generated context pack: `docs/context-packs/cab-2173.md`

- Primary component: `stoa-gateway`
- Impact Score: 68
- Impact Level: CRITICAL
- Modifier: -1.0
- Contracts: 20
- P0 scenarios: 1
- Untyped contracts: 5
- Open risks: 4

## Council Validation

### Chucky (Devil's Advocate) — 8.5/10

Verdict: Go

The ticket addresses a real semantic defect: the repo currently calls some standalone deployments "sidecar". Main risk is scope creep into a full gateway rewrite. Keep the first implementation bounded to one proven third-party gateway example, the route-gating tests, and footprint evidence.

Adjustments: keep service-mesh controller/injector out of scope; prove one real sidecar first.

### N3m0 (Webapp Security) — 8/10

Verdict: Go

No direct frontend surface is required. The relevant UX/DX risk is operator confusion between Edge MCP, Link, Connect, and mesh injection. Docs and Console wording must not imply sidecar when the runtime is standalone.

Adjustments: update docs and labels so operators can distinguish central gateway, true sidecar, and external connect agent.

### Gh0st (Supply Chain) — 8.5/10

Verdict: Go

The plan does not require new dependencies. The footprint section correctly pushes toward a lean sidecar image by disabling optional features unless explicitly needed. Current CI builds an enterprise-flavored image with `kafka,pingora`; sidecar packaging must not inherit that by accident.

Adjustments: document a lean image/profile and avoid new crates unless absolutely required.

### Pr1nc3ss (Social Engineering) — 8/10

Verdict: Go

The human risk is mis-selling "sidecar" when the deployment is not co-located. Correcting naming and docs reduces trust-boundary ambiguity. Deny responses must avoid leaking internal policy details.

Adjustments: keep deny messages generic by default; detailed diagnostics belong in logs/metrics.

### OSS Killer (VC Skeptique) — 9/10

Verdict: Go

True sidecar semantics are core to STOA's enterprise value proposition: co-pilot for existing gateways plus micro-gateway/mesh path. This strengthens differentiation against MCP-only gateway positioning.

Adjustments: preserve the "same core, different packaging" story in docs and evidence.

### Archi 50x50 (Architecte Veteran) — 8.5/10

Verdict: Go

The proposed shared decision pipeline is the right abstraction. Do not let protocol adapters duplicate authorization logic. Keep Edge MCP route behavior untouched and restrict sidecar changes to `/authz`, manifest packaging, and tests.

Adjustments: add regression tests proving sidecar has no MCP routes and calls the shared decision engine.

### Better Call Saul (Legal/IP) — 8/10

Verdict: Go

No license concern if no new dependencies are added. The DORA/regulated-customer angle improves when deployment semantics are truthful and evidence-backed. Avoid unverified claims about webMethods/Kong ext_authz compatibility beyond tested examples.

Adjustments: docs must mark examples as tested configurations, not universal vendor guarantees.

### Gekk0 (Monetisation / GTM) — 9/10

Verdict: Go

This is commercially aligned: "sidecar co-pilot for existing gateways" is easier to sell than "replace your gateway". Footprint measurements matter because broad app-side injection affects enterprise TCO.

Adjustments: archive binary/image/RSS numbers so sales/architecture discussions are evidence-backed.

## Initial Score

- Persona Average: 8.44/10
- Impact Score: 68 (CRITICAL)
- Impact Modifier: -1.0
- Final Score: 7.44/10
- Global Verdict: Fix before code

## Required Fixes Applied To Plan

The plan in CAB-2173 already includes the required fixes:

1. Explicitly no service-mesh controller/injector in this ticket.
2. Same core decision pipeline; adapters only differ by protocol/packaging.
3. Lean sidecar image/profile and measured RSS/image/binary evidence.
4. One real co-located third-party gateway example as the implementation proof.
5. Docs must distinguish Edge MCP, STOA sidecar/Link, STOA Connect, and micro-gateway/mesh.

## Adjusted Score

After applying the required fixes to the implementation plan:

- Persona Average: 9.13/10
- Impact Score: 68 (CRITICAL)
- Impact Modifier: -1.0
- Final Score: 8.13/10
- Global Verdict: Go with scope guardrails

## Execution Decision

Proceed with implementation only within the narrowed scope above.

Treat this as Council S2 Fix-then-Go: no code outside the stated files/behaviors without a new ticket or explicit scope update.
