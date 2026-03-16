# ADR-058: Pingora Integration — Embedded Connection Pool

**Status**: Accepted (Embed Pingora connector, keep axum for routing)
**Date**: 2026-03-16 (revised)
**Tickets**: CAB-1847, CAB-1849

## Context

Cloudflare's Pingora (Rust, Apache 2.0) replaced nginx and handles 1+ trillion requests/day. STOA Gateway is built on axum + reqwest + tokio. The question: how should STOA leverage Pingora?

## Why Pingora

### The Business Case (decisive factor)

| Signal | axum-only | With Pingora |
|--------|-----------|-------------|
| Enterprise pitch | "Custom Rust gateway" | **"Built on Pingora — Cloudflare's proxy framework"** |
| Competitive position | Same tier as custom proxies | **Same tier as Cloudflare Workers, Fastly Compute** |
| CISO checkbox | Unknown stack | **Battle-tested at 1T+ req/day** |
| OSS credibility | Generic framework | **Infrastructure-grade pedigree** |
| Market uniqueness | None | **Only API gateway built on Pingora** |

No API gateway vendor — Kong, Gravitee, Envoy, agentgateway — uses Pingora. This is a first-mover advantage in positioning.

### The Technical Case

| Feature | reqwest (current) | Pingora Connector |
|---------|-------------------|-------------------|
| Connection pool | Per-client instance | **Shared across all workers** (Cloudflare's key win) |
| H2 multiplexing | Per-connection | **Global stream multiplexing** |
| Pool reuse at scale | Degrades >10K RPS | **Designed for 1T+ req/day** |
| Zero-copy proxy | No (userspace copy) | Kernel splice/sendfile (future) |

At <1K RPS the difference is 0.5ms p95. At 50K+ RPS, shared pooling avoids connection exhaustion that per-client pools hit.

## Options Evaluated

| Option | Description | Effort | Verdict |
|--------|-------------|--------|---------|
| A: Full migration | Replace axum with Pingora server | 55+ pts | Rejected — rewrites 400+ routes |
| B: Sidecar | Pingora front-proxy → stoa-gateway | 21 pts | Rejected — extra hop, thin value |
| **C: Embedded** | **Pingora connector inside stoa-gateway** | **13 pts** | **Accepted** |
| D: Patterns only | Copy Pingora patterns, don't use crate | 0 pts | Superseded by C |

### Why Embedded (Option C) Won

- **One binary** — no sidecar, no extra hop, no deployment complexity
- **Same marketing claim** — "Built on Pingora" is equally true for embedded connector
- **Genuine value** — Pingora's shared pool is the actual Cloudflare advantage, not the server
- **Feature-gated** — `--features pingora` enables it; default build stays reqwest (no cmake dependency)
- **Incremental** — proxy path migrates to PingoraPool gradually; MCP/admin/auth stay on axum untouched

## Decision

**Embed `pingora-core::connectors::http::Connector` inside stoa-gateway behind a `pingora` feature flag.**

### Architecture

```
Client → stoa-gateway (:8080)
              │
              ├─ MCP / admin / auth / OAuth → axum handlers (unchanged)
              │
              └─ Proxy routes → PingoraPool.send_request()
                                    │
                                    └─ pingora-core shared connection pool
                                         → Backend (H1/H2, TLS, keepalive)
```

One binary. One port. One deployment. Pingora manages upstream connections; axum manages HTTP routing.

### Implementation (delivered in CAB-1849)

| PR | What |
|-----|------|
| #1799 | `stoa-pingora/` standalone binary (sidecar POC — superseded) |
| #1801 | `PingoraPool` embedded in stoa-gateway (production path) |
| #1803 | CI/CD: `FEATURES=kafka,pingora` in Docker build |

### Phase Compatibility

Our `ProxyPhase` trait (CAB-1834) maps 1:1 to Pingora's `ProxyHttp`:

| STOA ProxyPhase | Pingora ProxyHttp | Status |
|-----------------|-------------------|--------|
| `request_filter` | `request_filter` | Match |
| `upstream_select` | `upstream_peer` | Match |
| `upstream_request_filter` | `upstream_request_filter` | Match |
| `response_filter` | `upstream_response_filter` | Match |
| `logging` | `logging` | Match |
| `error_handler` | `error_while_proxy` | Match |

If a full Pingora migration is needed at v2.0, phase implementations port directly.

## What STOA Has That Pingora Doesn't

| Capability | STOA | Pingora |
|-----------|------|---------|
| eBPF kernel-level HTTP parsing | XDP + TC (CAB-1841/1843) | Not built-in |
| UAC policy enforcement at kernel level | BPF maps synced from gateway (CAB-1848) | Not built-in |
| WASM plugin runtime | wasmtime 42 (CAB-1644) | Not built-in |
| MCP protocol (AI agent gateway) | Full SSE/WS/JSON-RPC | Not applicable |
| Multi-gateway federation | 7 adapter types | Not applicable |

STOA uses Pingora for what it does best (connection pooling) and adds layers Pingora doesn't offer.

## Consequences

- Production image built with `FEATURES=kafka,pingora` (cmake required in Docker)
- `PingoraPool` available for proxy path; reqwest remains as fallback
- Default build (no features) still works without cmake dependency
- Marketing: **"STOA Gateway — powered by Pingora's connection engine"**
- NOTICE file includes Pingora Apache 2.0 attribution
- Re-evaluate full migration at v2.0 or 50K+ RPS
