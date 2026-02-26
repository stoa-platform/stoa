# Gateway Arena — Benchmark Results

> Last updated: 2026-02-26
>
> These results are a point-in-time snapshot from the continuous benchmark.
> Live results are available on the [Grafana dashboard](https://grafana.gostoa.dev).

## Layer 0 — Proxy Baseline

Measures raw throughput, burst handling, and ramp-up capacity.
All gateways proxy a local nginx echo backend (static JSON, <1 ms).

| Gateway | Environment | Score | CI95 Range | Rating |
|---------|-------------|-------|------------|--------|
| Kong 3.x (DB-less) | K8s (OVH MKS) | ~87 | 84-90 | Good |
| STOA Gateway (Rust) | K8s (OVH MKS) | ~73 | 70-76 | Acceptable |
| Gravitee 4.x | K8s (OVH MKS) | ~65 | 60-70 | Acceptable |
| STOA Gateway (Rust) | VPS (co-located) | ~78 | 75-81 | Acceptable |
| Kong 3.x (DB-less) | VPS (co-located) | ~85 | 82-88 | Good |

**Score interpretation**: 0-100 composite. >95 Excellent, 80-95 Good,
60-80 Acceptable, <60 Investigate.

### Key Observations

- Kong's mature proxy path delivers strong baseline throughput
- STOA's Rust gateway prioritizes MCP and middleware features over raw proxy speed
- VPS co-located benchmarks show slightly different profiles due to Docker networking
- All gateways handle burst scenarios without errors at the tested concurrency levels

## Layer 1 — Enterprise AI Readiness

Measures 8 enterprise dimensions including MCP protocol support, auth chains,
and AI guardrails.

| Gateway | MCP Support | Enterprise Score | CI95 Range |
|---------|-------------|-----------------|------------|
| STOA Gateway (Rust) | REST (native) | ~95 | 92-98 |
| Kong 3.x OSS | None (Enterprise-only plugin) | ~5 | 3-7 |
| Gravitee 4.x | Streamable HTTP | ~5 | 3-7 |

### Per-Dimension Breakdown (STOA Gateway)

| Dimension | Score | Notes |
|-----------|-------|-------|
| MCP Discovery | ~98 | Native REST endpoint, sub-100ms |
| MCP Tool Execution | ~95 | JSON-RPC tool listing |
| Auth Chain | ~92 | JWT + JWKS caching |
| Policy Engine | ~96 | OPA embedded evaluator |
| AI Guardrails | ~90 | PII detection middleware |
| Rate Limiting | ~98 | Per-consumer quotas |
| Resilience | ~95 | Graceful error handling |
| Agent Governance | ~88 | Session management endpoints |

### Why Other Gateways Score Low

Gateways without MCP protocol support score **0** on MCP dimensions (Discovery
and Tool Execution), which carry a combined weight of 0.35. The remaining
dimensions (Auth, Policy, Rate Limiting, Resilience) may return partial scores
if the gateway supports those features through standard HTTP paths, but without
the MCP-specific endpoints the composite score is structurally low.

This is by design: the Enterprise AI Readiness index measures AI-native gateway
capabilities. Any gateway can improve its score by implementing the open MCP
specification.

## Environment Details

| Parameter | Value |
|-----------|-------|
| K8s Cluster | OVH Managed Kubernetes (GRA9), 3x B2-15 nodes |
| Echo Backend | nginx:alpine, static JSON, <1 ms response |
| k6 Version | 0.54.0 |
| Benchmark Schedule | Every 30 min (Layer 0), hourly (Layer 1) |
| Statistical Method | Median of 4 valid runs, CI95 via t-distribution |

## Methodology

See [BENCHMARK-METHODOLOGY.md](BENCHMARK-METHODOLOGY.md) for the full scoring
formula, scenario definitions, and statistical method.

## Disclaimer

Benchmark results depend on hardware, network conditions, configuration, and
software versions. These results reflect a specific deployment environment and
may not be representative of all configurations. We encourage independent
verification using the [open-source benchmark scripts](../scripts/traffic/arena/).
