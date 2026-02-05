# STOA Gateway (Rust)

## Overview
Emerging Rust implementation of the unified STOA gateway. Will replace the Python mcp-gateway by Q4 2026. Implements the 4-mode architecture (ADR-024): edge-mcp, sidecar, proxy, shadow.

## Status: Work In Progress (Phase 12)
Currently implements: MCP discovery, tool proxy, JWT/OAuth2 auth, SSE transport, Prometheus metrics.

## Tech Stack
- Rust 2021 edition, Tokio 1 (async runtime), Axum 0.7 (web framework)
- serde/serde_json (serialization), Figment (layered config: YAML + env)
- jsonwebtoken 9 (JWT), reqwest 0.11 (HTTP client)
- moka 0.12 (in-memory cache for API keys + JWKS)
- prometheus 0.13, tracing/tracing-subscriber (structured JSON logging)
- tokio-stream, futures (SSE streams)

## Directory Structure
```
src/
├── main.rs              # Entry point + Axum router setup
├── main_wiring.rs       # Dependency injection / AppState construction
├── state.rs             # AppState (shared application state)
├── config.rs            # Figment-based layered configuration
├── metrics.rs           # Prometheus metrics registry
├── rate_limit.rs        # Rate limiting
├── auth/                # API key auth (api_key.rs), OAuth2, Keycloak OIDC
├── control_plane/       # Client for control-plane-api, tool proxy
├── handlers/            # Admin handlers
├── mcp/                 # MCP protocol implementation
│   ├── discovery.rs     # Capabilities, health, discovery
│   ├── session.rs       # Session management
│   ├── sse.rs           # Server-Sent Events transport
│   ├── handlers.rs      # Tool call, tool list
│   └── tools/           # proxy_tool, stoa_tools
├── proxy/               # Dynamic proxy, webmethods integration
├── routes/              # Route definitions
└── uac/                 # Universal API Contract
```

## Development
```bash
cargo check              # Fast compile check
cargo test               # Run tests
cargo clippy             # Lint
cargo fmt --check        # Format check
cargo run                # Run server
```

## Dependencies
- **Depends on**: control-plane-api (config/tool sync), Keycloak (JWT verification)
- **Depended on by**: nothing yet (will replace mcp-gateway)
