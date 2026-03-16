# ADR-058: Pingora-as-Library Evaluation — axum vs pingora-proxy

**Status**: Accepted (Keep axum, adopt patterns selectively)
**Date**: 2026-03-16
**Ticket**: CAB-1847

## Context

Cloudflare's Pingora (Rust, Apache 2.0) replaces nginx for 1+ trillion req/day. STOA Gateway is built on axum + reqwest + tokio. We implemented Pingora-inspired patterns in CAB-1827 (hot-reload, memory backpressure, TCP filtering, connection pool instrumentation, multi-upstream LB). The question: should we adopt `pingora-proxy` as a library?

## Evaluation

### Phase Comparison

| Phase | Pingora ProxyHttp | STOA ProxyPhase (CAB-1834) | Gap |
|-------|-------------------|---------------------------|-----|
| Early request filter | `early_request_filter` | — | Low (pre-module, niche) |
| Request filter | `request_filter` | `request_filter` | None |
| Request body filter | `request_body_filter` (chunked) | — | Medium (streaming WAF) |
| Cache filter | `request_cache_filter` | — | Medium (HTTP caching) |
| Upstream select | `upstream_peer` | `upstream_select` | None |
| Upstream request filter | `upstream_request_filter` | `upstream_request_filter` | None |
| Upstream response filter | `upstream_response_filter` | `response_filter` | None |
| Response body filter | `response_body_filter` (chunked) | — | Medium (streaming transform) |
| Logging | `logging` | `logging` | None |
| Error handler | `error_while_proxy` + `fail_to_proxy` | `error_handler` | None |

**Score**: 6/10 phases match. Gaps are body filters (streaming) and HTTP caching — neither needed for MCP gateway.

### Architecture Comparison

| Feature | Pingora | STOA (current) | Migration Cost |
|---------|---------|----------------|---------------|
| HTTP server | Custom (pingora-core) | axum (hyper) | **Very High** — rewrite all routes |
| Connection pool | Shared cross-worker, H2 mux | Per-reqwest-client | Medium — adopt pingora-core pool |
| Zero-copy proxy | splice/sendfile | reqwest streaming | High — kernel API, Linux-only |
| TLS | BoringSSL (pingora-openssl) | rustls (reqwest) | High — different TLS stack |
| HTTP caching | Built-in (pingora-cache) | None | N/A — not needed for MCP |
| Load balancing | pingora-load-balancing | Custom (CAB-1833) | Low — similar design |
| Zero-downtime upgrade | Built-in fd passing | Not implemented (CAB-1835 won't fix) | N/A — K8s handles this |
| eBPF integration | Not built-in | Custom (CAB-1841/1843/1848) | N/A — our differentiator |
| Plugin system | Not built-in | Native + WASM (CAB-1759/1644) | N/A — our differentiator |

### Performance Analysis (Arena L0)

| Gateway | Score | p95 Sequential | p95 Burst50 |
|---------|-------|----------------|-------------|
| echo-baseline (nginx) | 82.39 | 4.4ms | 278ms |
| stoa-k8s (axum+reqwest) | 81.93 | 4.9ms | 297ms |

**Delta: 0.5ms p95 overhead** — the proxy engine is NOT the bottleneck. At current traffic levels (<1K RPS), Pingora's advantages (shared pool, zero-copy) provide negligible benefit. These matter at >100K RPS.

### Hybrid Approach Feasibility

**Option A: Full migration** — Replace axum with Pingora server
- Pros: Native connection pool, zero-copy, battle-tested
- Cons: Rewrite ~400 axum routes (MCP, admin, OAuth, WebSocket, SOAP, A2A), lose axum middleware ecosystem, BoringSSL vs rustls conflict
- Effort: **55+ pts (multi-sprint)**
- Verdict: **Not viable before v2.0**

**Option B: Hybrid (two listeners)** — Axum for MCP/admin, Pingora for proxy path
- Pros: Proxy path gets Pingora benefits, MCP routes unchanged
- Cons: Two servers on different ports, nginx routing complexity, shared state between runtimes
- Effort: **21 pts**
- Verdict: **Possible but premature**

**Option C: Selective adoption** — Use Pingora patterns, not crates
- Pros: Zero migration cost, same performance profile, our eBPF layer is deeper than Pingora's
- Cons: Miss shared connection pool (biggest Pingora win)
- Effort: **0 pts (already done in CAB-1827)**
- Verdict: **Current approach, validated by benchmarks**

## Decision

**Keep axum + reqwest. Continue selective pattern adoption.**

### Rationale

1. **Performance is not the bottleneck** — 0.5ms overhead at p95. Pingora's wins (shared pool, zero-copy) matter at >100K RPS. STOA is pre-v1.0.
2. **Migration cost is prohibitive** — 400+ routes on axum, MCP protocol deeply integrated, BoringSSL vs rustls would break OAuth/mTLS stack.
3. **Our eBPF layer goes deeper** — Pingora doesn't have kernel-level HTTP parsing or UAC policy enforcement. Our XDP+TC stack is a competitive advantage Pingora doesn't offer.
4. **ProxyPhase trait is compatible** — Our 6-phase design (CAB-1834) maps cleanly to Pingora's ProxyHttp. If we migrate later, the phase implementations port directly.
5. **Pingora is pre-1.0** (0.8.0) — API stability not guaranteed.

### Re-evaluation Triggers

- Traffic exceeds 50K RPS sustained (connection pool becomes critical)
- Pingora reaches 1.0 with stable API
- HTTP caching becomes a requirement (Pingora has built-in cache)
- reqwest connection pool proves inadequate under load (monitor via CAB-1832 pool metrics)

## Consequences

- Continue using axum + reqwest + tokio stack
- Monitor pool metrics (CAB-1832) for connection reuse degradation
- ProxyPhase trait (CAB-1834) designed for future Pingora compatibility
- eBPF stack (CAB-1841/1843/1848) remains our unique differentiator
- Revisit at v2.0 or when traffic triggers re-evaluation
