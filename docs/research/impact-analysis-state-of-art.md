# Impact Analysis & Dependency Tracking — State of the Art (2026)

> Practical findings for STOA Platform (~10 services, Rust/Python/React monorepo).
> Last updated: 2026-03-26

---

## 1. Dependency Tracking at Scale

### Backstage.io System Model (Spotify)

Backstage models software using five entity types: **Component** (a deployable unit — service, library, website), **API** (first-class citizen describing a contract — OpenAPI, gRPC, Async), **Resource** (infrastructure — S3, DB, Kafka topic), **System** (logical grouping of components sharing an owner), and **Domain** (high-level business capability). Relations (`dependsOn/dependencyOf`, `providesApi/consumesApi`, `ownedBy/ownerOf`) are the core of impact analysis — they let you ask "what breaks if I change this?"

**Key 2025 insight**: Healthy catalogs are measured by *relation quality*, not entity totals. A catalog with 50 components but accurate `dependsOn` relations is more valuable than 500 component cards with no relations. The highest-value fields per component are `spec.owner`, `spec.lifecycle`, `spec.type`, and system placement.

**At our scale (10 services)**: Backstage's model is the right *concept* but full Backstage is overkill — it requires a React frontend, PostgreSQL, and ongoing maintenance. The entity schema (YAML `catalog-info.yaml` per repo) is the reusable part.

**Recommendation for STOA**: Adopt the Backstage YAML schema (`catalog-info.yaml`) as a lightweight metadata standard per component, stored in each component's directory. Parse these files into a SQLite catalog (see Section 2) rather than running Backstage itself.

---

### Kubernetes SIG Architecture Patterns

K8s uses dependency tracking at two levels: **compile-time** (Go module graph enforced via `vendor/modules.txt` and staging/src symlinks) and **runtime** (owner references in resource manifests enabling garbage collection cascades). The key pattern is *explicit ownership declarations in manifests* — every resource carries metadata identifying its parent and its dependents.

**Applicable pattern**: Owner references / parent pointers in Helm chart annotations. STOA already uses ArgoCD applications per component — adding `app.gostoa.dev/depends-on` annotations to Helm values would enable automated impact analysis at the K8s layer.

---

### Google's Approach (deps.dev + Service Weaver)

Google's `deps.dev` (Open Source Insights) builds a global dependency graph for npm, PyPI, Go, Cargo, and Maven packages — scanning transitive dependencies and flagging security/license issues. As of 2025, the average application contains 1,200+ OSS components; 64% are transitive.

Service Weaver takes a different angle: write the application as a monolith with typed component interfaces, deploy as microservices. The framework infers the dependency graph from Go interface declarations — no manual catalog needed. Components are split at deploy time based on the call graph.

**At our scale**: Service Weaver is interesting for Go (stoa-go) but doesn't apply to our polyglot monorepo. deps.dev's approach (graph from package manifests) is the right pattern for automated OSS dependency tracking.

---

### Uber's Approach (CRISP + Jaeger)

Uber runs ~6,000 microservices. Their key tool is **CRISP** — Critical Path Analysis built on top of Jaeger distributed traces. CRISP extracts production dependency graphs from actual RPC traces, then generates critical-path heatmaps and flame graphs showing which services are on the hot path for a given user request. Dependencies are *inferred from production traffic*, not declared in catalogs.

**At our scale**: Most of CRISP is overkill. The key insight is **trace-derived dependency graphs** — if you have OpenTelemetry traces, you have your service dependency graph for free. For STOA, adding `traceparent` propagation through the Gateway (CAB-1350) means Jaeger/Tempo automatically builds the live dependency graph.

---

### AWS Well-Architected Dependency Mapping

AWS recommends **tiered criticality** (T0 = life-safety, T1 = revenue-critical, T2 = degraded-ok) and tracking dependencies as *first-class operational metadata*. The Well-Architected Reliability pillar requires explicit upstream/downstream dependency documentation for each workload, with recovery time objectives per tier.

**Recommendation for STOA**: Assign criticality tiers to our 10 services (Gateway = T1, Auth = T1, API = T1, Portal/Console = T2, Arena bench = T3). Store in `catalog-info.yaml`.

---

## 2. Impact Analysis Tooling

### Code-Level: madge / pydeps / cargo-depgraph

| Tool | Language | What it does | CI use |
|------|----------|-------------|--------|
| `madge` v8 | JS/TS | Module import graph, circular dependency detection | `madge --circular src/` |
| `pydeps` v3 | Python | Package-level dependency visualization (graphviz) | `pydeps src/ --max-bacon=4` |
| `cargo-depgraph` | Rust | Crate dependency graph from `Cargo.lock` | `cargo depgraph | dot -Tpng` |

**At our scale**: These are useful for *intra-component* circular dependency detection in CI. Run `madge --circular` on portal and control-plane-ui; `pydeps` on control-plane-api to catch accidental cross-layer imports. For Rust, `cargo tree` (built-in) covers most needs.

**Overkill warning**: Full graphviz renders of the entire codebase don't scale to daily CI — use only for targeted audits or on-demand.

---

### Service-Level: Backstage vs Port.io vs Cortex.io

| Tool | Best for | Dependency features | Setup cost |
|------|----------|-------------------|------------|
| **Backstage** | Large orgs (100+ services), self-hosted | `dependsOn` relations, catalog graph UI | High (maintain a React app) |
| **Port.io** | Platform teams, 20-200 services | Custom entity graphs, scorecards, ripple-effect views | Medium (3-6 months to full value) |
| **Cortex.io** | Mid-market, out-of-box governance | Auto-sync from Datadog traces, API deprecation alerts | Low-medium (SaaS, opinionated) |

**At our scale**: None of these are justified yet. The right move is a **SQLite catalog** seeded from `catalog-info.yaml` files (Backstage schema) and OpenAPI specs, queried by our `/impact` skill and `/carto` skill. Port or Cortex become relevant at 30+ services.

---

### Auto-Generated Dependency Maps

Three reliable sources for auto-generation:

1. **OpenAPI `$ref` analysis**: Parse OpenAPI specs to extract which services expose which schemas. Cross-reference `consumesApi` fields in `catalog-info.yaml` to build a service API dependency matrix.
2. **Import graph analysis**: `madge` for TS, `pydeps` for Python, `cargo tree` for Rust — run in CI, store results as JSON in `.claude/carto-cache/`.
3. **OTel trace-derived graphs**: Query Tempo/Jaeger for `service.name` span relationships. This gives *runtime* dependencies vs *declared* ones. Diff between declared and observed = hidden dependencies.

**Recommendation for STOA**: The `/carto` skill should combine (1) static `catalog-info.yaml` parsing + (2) OpenAPI cross-reference + (3) optional OTel query. Store in SQLite at `.claude/carto.db`. Refresh on every merge to main.

---

### SQLite vs Full Service Mesh Observability

| Approach | Best for | Cost | Accuracy |
|----------|----------|------|----------|
| SQLite + YAML catalog | <30 services, monorepo | Near-zero | Declared dependencies only |
| Service mesh (Istio/Linkerd) | >50 services, multi-cluster | High (sidecar overhead) | Runtime + declared |
| OTel + Tempo/Jaeger | Any scale | Medium (infra already exists) | Runtime only |

**For STOA**: SQLite + YAML is the right tier now. We already have OTel traces via the Gateway — use them for validation, not as primary catalog.

---

## 3. Scenario-Based Testing Patterns

### Contract Testing (Pact)

Consumer-driven contract testing: the **consumer** writes a test that records its expectations of the provider's API into a **pact file**; the **provider** verifies it can satisfy that pact independently. No shared environment needed.

**Strengths**: Fast (no live services), catches breaking API changes before deployment, fits CI perfectly. **When it shines**: 3+ services that exchange data over HTTP/events.

**At our scale**: Pact is well-justified for the Gateway ↔ Control Plane API boundary and the Portal ↔ API boundary. Not warranted for internal Gateway handler calls. Implementation: consumer = stoa-gateway Rust tests writing pact files; provider = control-plane-api pytest verifying them. Pact Broker (self-hosted) or PactFlow (SaaS) stores contracts.

**Overkill signal**: If a team owns both consumer and consumer — skip Pact, use integration tests.

---

### OpenTelemetry Trace-Based Testing

The OTel Demo project demonstrated trace-based tests in 2023: trigger an endpoint, then assert that the resulting distributed trace matches an expected shape (spans present, attributes set, no error spans). This validates *cross-service behavior* using production-identical instrumentation.

**Pattern**: Record a "golden trace" in staging → assert each new deployment produces a structurally equivalent trace for the same scenario. Tools: `tracetest.io` (OSS, purpose-built), or custom assertions against Tempo's query API.

**At our scale**: High value for MCP tool calls that cross Gateway → API → external service. The full MCP invocation path (Claude.ai → Gateway → Tool → CP API) is exactly the kind of multi-hop scenario trace-based testing was designed for. Tracetest integrates with OTel natively and runs in CI.

**Recommendation**: Implement trace-based tests for the 3 critical CUJs already defined in the Arena L2 verify job (health chain, auth flow, MCP discovery→call). These already exist as curl scripts — migrate them to Tracetest assertions.

---

### Synthetic Monitoring / Synthetic Transactions

Synthetic monitoring scripts scripted user journeys continuously from external probes — not waiting for real users to hit a path. Key 2025 pattern: AI-powered anomaly detection that sets baselines without manual thresholds, and self-healing scripts that adapt to UI changes.

**STOA already has this**: The Arena L2 CronJob (`run-arena-verify.sh`) runs the 3 CUJs every 15 minutes and pushes to Prometheus. This is textbook synthetic transaction monitoring. The gap is correlation with backend traces — when L2 reports a failing CUJ, there's no automatic drill-down to which service caused it.

**Improvement**: Add `traceparent` headers to L2 synthetic requests. When a CUJ fails, the trace ID is in the response headers → direct link to Tempo trace in the alert.

---

### How Large Orgs Trace User Journeys

- **Netflix**: Chaos Engineering generates failure scenarios, production traffic mirrors validate recovery. Dependency graphs come from Zuul API gateway logs.
- **Google (DORA research)**: Change Failure Rate tracked per service from deploy events + incident alerts. No single tracing tool — aggregated from Spanner audit logs.
- **Uber (CRISP)**: All user journeys instrumented with Jaeger. CRISP extracts critical paths, identifies the single service most likely to cause latency for a given journey. Impact analysis = "which service is on the critical path for Ride Request?"

**Common pattern across all three**: Runtime traces are the source of truth for dependency graphs. Catalog declarations are validated against observed traces — discrepancies flagged as hidden dependencies.

---

## Summary Recommendations for STOA

| Area | Recommended Action | Priority |
|------|-------------------|----------|
| Catalog | Add `catalog-info.yaml` to each component with Backstage schema | High |
| Code deps | `madge --circular` in portal/ui CI, `cargo tree` for gateway | Medium |
| SQLite catalog | `/carto` skill parses catalog-info + OpenAPI specs into `.claude/carto.db` | High |
| Contract testing | Pact for Gateway ↔ CP API boundary | Medium |
| Trace-based testing | Migrate L2 CUJs to Tracetest with OTel assertions | Medium |
| Synthetic enhancement | Add `traceparent` to Arena L2 verify requests | Low |
| Tier labels | Tag services T1/T2/T3 in `catalog-info.yaml` + Helm annotations | Low |

**Not recommended now** (overkill for 10 services): Full Backstage deployment, Istio service mesh, Port.io or Cortex.io SaaS, CRISP-style critical path analysis.
