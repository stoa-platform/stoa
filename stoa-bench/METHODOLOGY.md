# STOA Bench — Methodology & Transparency

> Last verified: 2026-03-08

## Overview

STOA Bench is a 4-layer continuous benchmark comparing API gateway capabilities
for AI-native workloads. All gateways run on the same infrastructure with the
same echo backend to ensure fair comparison.

## Gateways Benchmarked

| Gateway | Version | License | L0 | L1 | Notes |
|---------|---------|---------|----|----|-------|
| STOA Gateway | latest (main) | Apache 2.0 | Yes | Yes (all 20 dims) | MCP REST protocol |
| agentgateway | v1.0.0-alpha.4 | Apache 2.0 (LF) | Yes | Yes (6 features) | MCP Streamable HTTP |
| Kong OSS | 3.9.1 | Apache 2.0 | Yes | Yes (0 features) | No MCP support |
| Gravitee APIM | 4.x | Apache 2.0 (CE) | No* | Yes (5 features) | MCP Streamable HTTP |

\* Gravitee L0 disabled due to health probe incompatibility with APIM 4.6.

### Kong Enterprise (Not Benchmarked)

Kong Enterprise 3.12+ includes the **AI MCP Proxy** plugin with significant
AI capabilities (~14/20 dimensions). However:

- Requires a paid license (not freely available for benchmarking)
- License terms may restrict benchmark publication
- Kong OSS 3.10+ removed free Docker images

We include Kong OSS as the freely deployable baseline. Kong Enterprise users
should expect significantly higher L1 scores than Kong OSS.

## Scoring

### L0 — Proxy Baseline

Pure proxy performance (latency, throughput, error rate). No MCP, no AI features.

**Formula**: `0.15*Base + 0.25*Burst50 + 0.25*Burst100 + 0.15*Avail + 0.10*Error + 0.10*Consistency`

- 7 scenarios: warmup, health, sequential(20), burst_10/50/100, sustained(100)
- Caps: 400ms sequential, 2.5s burst_50, 4s burst_100
- Consistency: IQR-based coefficient of variation
- **Statistical method**: median of 5 runs (1 warm-up discarded), CI95 confidence intervals

### L1 — Enterprise AI Readiness

20 dimensions across 5 categories, measuring AI-native gateway capabilities.

**Feature gate**: Gateways declare supported `features` in the benchmark config.
Missing features score 0 (not N/A). This is intentional — a gateway without MCP
should score 0 on MCP dimensions, not be excluded from comparison.

**Composite score**: `sum(weight_i * dimension_i)`

Each dimension: `0.6 * availability + 0.4 * latency_score`

Latency score: `max(0, 100 * (1 - p95/cap))`

| Category | Dimensions | Weight | Key Dimensions |
|----------|------------|--------|----------------|
| Core Gateway | 8 | 0.51 | MCP Discovery (0.10), MCP Tool Call (0.08), Auth Chain (0.08) |
| LLM Intelligence | 3 | 0.17 | LLM Routing (0.07), Cost Control (0.05) |
| MCP Depth | 3 | 0.13 | Native Tools CRUD (0.05), API Bridge (0.04), UAC Binding (0.04) |
| Security & Compliance | 3 | 0.10 | PII Detection (0.04), Distributed Tracing (0.03) |
| Platform Ops | 3 | 0.09 | Skills Lifecycle (0.03), Federation (0.03) |

**L1-A / L1-B split**:
- L1-A (Gateway Core, 40% weight): traditional gateway capabilities
- L1-B (AI-Native, 60% weight): MCP, LLM, and AI-specific features

### L2 — Platform CUJs (Critical User Journeys)

5 CUJs validating the full platform demo flow:

| CUJ | Name | Demo Blocker? | Threshold |
|-----|------|---------------|-----------|
| CUJ-01 | API Discovery | Yes | < 2000ms |
| CUJ-02 | Subscription Self-Service | Yes | < 30000ms |
| CUJ-03 | Observability Pipeline | No (degraded) | Metrics < 30s, Logs < 60s |
| CUJ-04 | Auth Federation | No (degraded) | < 500ms |
| CUJ-05 | MCP Tool Exposure | Yes | < 3000ms |

### L3 — Stability Analysis

Automated analysis running after each L2 cycle:
- **Consecutive PASS tracking**: HIGH (≥50), MEDIUM (≥10), LOW (>0), BLOCKED (0)
- **Regression detection**: 15% threshold on latency degradation
- **Flakiness detection**: <95% pass rate flags flaky CUJs

## Feature Matrix (L1 Dimensions)

| # | Dimension | STOA | agentgateway | Kong OSS | Gravitee |
|---|-----------|------|-------------|----------|----------|
| 1 | MCP Discovery | Yes | Yes | No | Yes |
| 2 | MCP Tool Call | Yes | Yes | No | Yes |
| 3 | Auth Chain | Yes | Yes | Yes | Yes |
| 4 | Policy Engine | Yes | Yes (CEL) | Yes | Yes |
| 5 | Guardrails | Yes | Yes | No | Yes |
| 6 | Rate Limit | Yes | Yes | Yes | Yes |
| 7 | Resilience | Yes | Yes | Yes | Yes |
| 8 | Governance | Yes | Yes | Yes | Yes |
| 9 | LLM Routing | Yes | Yes | No | Yes |
| 10 | LLM Cost Control | Yes | Yes | No | Yes |
| 11 | LLM Circuit Breaker | Yes | No | No | No |
| 12 | Native Tools CRUD | Yes | Partial | No | No |
| 13 | API→MCP Bridge | Yes | Yes | No | Yes |
| 14 | UAC Binding | Yes | No | No | No |
| 15 | PII Detection | Yes | Yes | No | No |
| 16 | Distributed Tracing | Yes | Yes | No | Yes |
| 17 | Prompt Cache | Yes | No | No | No |
| 18 | Skills Lifecycle | Yes | No | No | No |
| 19 | Federation | Yes | Yes | No | No |
| 20 | Diagnostic | Yes | Partial | No | No |

**UAC Binding** (#14) is a STOA-unique concept (Universal API Contract).
No other gateway implements this — it is genuinely differentiated, not a
benchmark artifact.

## Infrastructure

All gateways run in the same K8s cluster (OVH MKS GRA9, 3x B2-15 nodes)
with a shared echo backend (nginx, static JSON, <1ms response time).

This ensures benchmarks measure **gateway overhead only**, not backend variability.

## Limitations & Disclaimers

1. **Alpha software**: agentgateway v1.0.0-alpha.4 is pre-release. Scores may
   improve significantly as the project matures.
2. **Enterprise features excluded**: Kong Enterprise, Gravitee Enterprise, and
   other paid tiers are not benchmarked. Only freely available versions are tested.
3. **Feature declarations are manual**: The `features` array is maintained by the
   STOA team based on public documentation. Inaccuracies should be reported as
   issues on the STOA repository.
4. **Point-in-time snapshot**: Scores reflect gateway capabilities as of the
   `last verified` date. Gateway vendors ship updates continuously.
5. **Not a product ranking**: This benchmark measures specific technical
   capabilities. Production suitability depends on many factors not captured here
   (support, ecosystem, community, enterprise features, compliance certifications).

## Reproducibility

All benchmark code is open source (Apache 2.0):
- k6 scripts: `scripts/traffic/arena/`
- Scoring: `stoa-bench/scoring/`
- K8s manifests: `k8s/arena/`
- Docker image: `ghcr.io/stoa-platform/arena-bench:0.2.0`

To reproduce: deploy the arena on any K8s cluster and run the CronJobs.
