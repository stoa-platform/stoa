# Gateway Arena Benchmark — Methodology

> Transparent scoring methodology for the STOA Gateway Arena benchmark.
> Last updated: 2026-03-11

## Overview

The Gateway Arena measures API gateway performance across three layers:

| Layer | What It Measures | Frequency | Gateways |
|-------|-----------------|-----------|----------|
| **L0** — Proxy Baseline | Raw proxy overhead (latency, throughput, availability) | Every 30 min | 5 (echo-baseline, STOA, agentgateway, Kong OSS, Gravitee) |
| **L1** — Enterprise AI Readiness | 20-dimension AI-native gateway capabilities | Hourly | 4 (STOA, agentgateway, Gravitee, Kong OSS) |
| **L2** — Platform Health | 3 Critical User Journeys (health, auth, MCP) | Every 15 min | STOA only (production SLA) |

## Fair Comparison Principles

1. **Shared echo backend**: All gateways proxy the same nginx echo service returning static JSON (<1ms). Benchmarks measure gateway overhead only.
2. **Same hardware**: All K8s gateways run on the same OVH MKS cluster (3x B2-15 nodes, 4 vCPU / 15 GB each). VPS benchmarks run on co-located Docker hosts.
3. **Statistical rigor**: Median of 5 runs (1 warm-up discarded), 95% confidence intervals using Student's t-distribution.
4. **Self-declared features**: Each gateway declares which L1 features it supports. Missing feature = score 0 (not N/A). Any vendor can submit corrections.
5. **Open source**: Benchmark scripts, scoring formulas, and this methodology are public in the STOA repository under Apache 2.0.

## Gateway Versions (Pinned)

| Gateway | Version | Image | Type | Licence |
|---------|---------|-------|------|---------|
| **STOA** | latest (main) | `ghcr.io/stoa-platform/stoa-gateway:latest` | AI-native MCP gateway | Apache 2.0 (OSS) |
| **agentgateway** | v1.0.0-alpha.4 | `ghcr.io/agentgateway/agentgateway:v1.0.0-alpha.4` | AI-native MCP gateway | Apache 2.0 (LF OSS) |
| **Gravitee APIM** | 4.10 | `graviteeio/apim-gateway:4.10` | Traditional API gateway | Enterprise (AI features paid) |
| **Kong OSS** | 3.9.1 | `kong:3.9.1-ubuntu` | Traditional API gateway | Apache 2.0 (OSS) |
| **echo-baseline** | — | `nginx:1.25-alpine` | Reference (0-overhead) | — |

### Evaluated But Not Included

**Kong Gateway Enterprise** (AI License): Evaluated for L1 inclusion. Kong ships 21 AI plugins (6 OSS + 15 AI License) including MCP Proxy (3.12+, Tech Preview) and AI Proxy Advanced. However:
- The AI License is a separate commercial add-on, not available for automated CI benchmarking
- MCP plugins are in Tech Preview (not GA)
- No self-hosted trial image available for reproducible testing

Kong Enterprise remains welcome to participate — see "Open Invitation" below.

## L0 — Proxy Baseline Scoring

### Scenarios (7)

| Scenario | VUs | Duration | What It Tests |
|----------|-----|----------|--------------|
| health | 1 | 5s | Health check latency |
| sequential | 1 | 10s | Single-user proxy latency |
| burst_10 | 10 | 10s | Light concurrency |
| burst_50 | 50 | 10s | Medium concurrency |
| burst_100 | 100 | 10s | Heavy concurrency |
| sustained | 20 | 30s | Steady-state throughput |
| ramp_up | 1→50 | 30s | Scaling behavior |

### Scoring Formula

```
L0_Score = 0.15 * base_score
         + 0.20 * burst_50_score
         + 0.10 * burst_100_score
         + 0.15 * availability_score
         + 0.10 * error_score
         + 0.15 * consistency_score
         + 0.15 * ramp_score
```

**Latency scoring**: `score = max(0, 100 * (1 - p95 / cap))`

| Metric | Cap (p95) | Weight | Rationale |
|--------|----------|--------|-----------|
| Base (sequential) | 400ms | 0.15 | Core proxy latency |
| Burst 50 | 2.5s | 0.20 | Realistic concurrency |
| Burst 100 | 4.0s | 0.10 | Downweighted: measures cluster capacity, not gateway |
| Availability | 100% = 100 | 0.15 | Request success rate |
| Error rate | 0% = 100 | 0.10 | HTTP error ratio |
| Consistency | IQR-based CV | 0.15 | Latency stability |
| Ramp-up | Degradation ratio | 0.15 | Performance under increasing load |

**Interpretation**: >95 excellent, 80-95 good, 60-80 acceptable, <60 investigate.

## L1 — Enterprise AI Readiness Scoring

### 20 Dimensions (5 Categories)

#### Core (8 dimensions, total weight: 0.51)

| Dimension | Weight | Requires MCP | Latency Cap | What It Tests |
|-----------|--------|-------------|-------------|--------------|
| mcp_discovery | 0.08 | Yes | 0.5s | MCP `tools/list` endpoint |
| mcp_toolcall | 0.10 | Yes | 0.5s | MCP `tools/call` execution |
| auth_chain | 0.08 | Yes | 1.0s | OAuth/JWT authentication on MCP |
| policy_eval | 0.06 | Yes | 0.2s | Policy enforcement on requests |
| guardrails | 0.06 | Yes | 1.0s | Content safety filters |
| quota_burst | 0.05 | No | 1.0s | Token-based rate limiting |
| resilience | 0.05 | Yes | 1.0s | Retry/circuit-breaker behavior |
| governance | 0.03 | No | 2.0s | Audit and governance controls |

#### LLM Intelligence (3 dimensions, total weight: 0.17)

| Dimension | Weight | Latency Cap | What It Tests |
|-----------|--------|-------------|--------------|
| llm_routing | 0.07 | 2.0s | Model/provider routing |
| llm_cost | 0.05 | 2.0s | Cost tracking per request |
| llm_circuit_breaker | 0.05 | 2.0s | Circuit breaker on LLM failures |

#### MCP Depth (3 dimensions, total weight: 0.13)

| Dimension | Weight | Latency Cap | What It Tests |
|-----------|--------|-------------|--------------|
| native_tools_crud | 0.05 | 1.0s | Tool definition lifecycle |
| api_bridge | 0.04 | 2.0s | REST-to-MCP transformation |
| uac_binding | 0.04 | 2.0s | Universal API Contract binding |

#### Security & Compliance (3 dimensions, total weight: 0.10)

| Dimension | Weight | Latency Cap | What It Tests |
|-----------|--------|-------------|--------------|
| pii_detection | 0.04 | 0.5s | PII redaction in transit |
| distributed_tracing | 0.03 | 0.5s | W3C traceparent propagation |
| prompt_cache | 0.03 | 2.0s | Semantic response caching |

#### Platform Operations (3 dimensions, total weight: 0.09)

| Dimension | Weight | Latency Cap | What It Tests |
|-----------|--------|-------------|--------------|
| skills_lifecycle | 0.03 | 1.0s | Skill deploy/undeploy/version |
| federation | 0.03 | 2.0s | Multi-gateway tool federation |
| diagnostic | 0.03 | 2.0s | Runtime health diagnostics |

### Scoring Formula

For each dimension:
```
dimension_score = check_pass_rate * max(0, 100 * (1 - p95 / latency_cap))
```

Composite enterprise score:
```
L1_Score = sum(dimension.weight * dimension.score for all dimensions)
```

### Feature Gate Logic

Each gateway declares a `features` array. The scoring pipeline checks:
1. If dimension `requires_mcp` and gateway has no `mcp_base` → score 0
2. If dimension `requires_feature` and feature not in gateway's `features` array → score 0
3. Otherwise → run the k6 scenario and compute score from pass rate + latency

Missing feature = 0 points (not excluded from the denominator). This means gateways are compared on the same 100-point scale regardless of feature set.

### Current Feature Declarations

| Feature | STOA | agentgateway | Gravitee 4.10 | Kong OSS |
|---------|------|-------------|---------------|----------|
| llm_routing | Yes | Yes | — | — |
| llm_cost | Yes | Yes | — | — |
| llm_circuit_breaker | Yes | Yes | — | — |
| native_tools_crud | Yes | Yes | — | — |
| api_bridge | Yes | Yes | — | — |
| uac_binding | Yes | — | — | — |
| pii_detection | Yes | Yes | — | — |
| distributed_tracing | Yes | Yes | Yes | — |
| prompt_cache | Yes | — | — | — |
| skills_lifecycle | Yes | — | — | — |
| federation | Yes | Yes | — | — |
| diagnostic | Yes | — | — | — |
| quota_burst | _(core)_ | _(core)_ | Yes | — |
| resilience | _(core)_ | _(core)_ | Yes | — |

## L2 — Platform Continuous Verification

3 Critical User Journeys every 15 minutes (STOA production only):
1. **Health chain**: API + Gateway + Keycloak return 2xx
2. **Auth flow**: OIDC client_credentials → authenticated MCP call
3. **MCP Discovery→Call**: Full MCP tool discovery and invocation

## Statistical Method

- **Runs per benchmark**: 5 (configurable via `RUNS` env var)
- **Warm-up**: First run discarded (`DISCARD_FIRST=1`)
- **Central tendency**: Median (robust to outliers)
- **Confidence intervals**: Student's t-distribution, 95% CI
- **Outlier handling**: IQR-based consistency metric in L0
- **Timeout**: 5s per request (L0), 10s per request (L1)

## Infrastructure

| Environment | Hardware | Network |
|-------------|----------|---------|
| K8s (primary) | OVH MKS GRA9, 3x B2-15 (4 vCPU, 15 GB) | Cluster-internal (ClusterIP) |
| VPS (secondary) | OVH VPS, Docker, co-located gateways | Host network (Docker) |

Metrics pushed to Prometheus Pushgateway → scraped by Prometheus → visualized in Grafana.

## Open Invitation

We welcome gateway vendors to participate in the Arena benchmark:

1. **Submit feature corrections**: If your gateway supports a dimension we haven't declared, open a GitHub issue with evidence (documentation link, API example).
2. **Add your gateway**: Fork the repository, add your gateway to the GATEWAYS JSON in `k8s/arena/cronjob-enterprise.yaml`, and submit a PR.
3. **Challenge methodology**: If you believe the scoring weights, latency caps, or test scenarios are unfair, open a discussion. We aim for defensible, not favorable.

All benchmark code is open source under Apache 2.0. We commit to re-running benchmarks within 30 days of receiving a valid correction.

## Changelog

| Date | Change |
|------|--------|
| 2026-03-11 | v2: 5 gateways (L0), 4 gateways (L1), METHODOLOGY.md created |
| 2026-02-28 | v1: 2 gateways (L0: STOA + echo), 2 gateways (L1: STOA + agentgateway) |
