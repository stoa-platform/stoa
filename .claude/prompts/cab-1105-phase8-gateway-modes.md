CAB-1105 Phase 8: 4-Mode Architecture + Shadow Discovery — capstone feature.

Branch: `feat/cab-1105-gateway-modes` (creer depuis main, APRES merge de feat/cab-1105-kill-python)

## Contexte
Le stoa-gateway Rust supporte actuellement un seul mode (edge-mcp). On veut 4 modes dans un seul binaire,
selectionne a runtime via `STOA_GATEWAY_MODE`. Le mode Shadow est le killer feature (decouverte automatique d'APIs).

Prerequis: les Phases 1-7 (feat/cab-1105-kill-python) doivent etre mergees dans main avant de commencer.
Lire `stoa-gateway/src/` pour comprendre la structure actuelle.

## Architecture

```
STOA_GATEWAY_MODE=edge_mcp (default)  → Full MCP: SSE + auth + tools + metrics
STOA_GATEWAY_MODE=sidecar             → Lightweight: auth + rate limit + metrics only
STOA_GATEWAY_MODE=proxy               → Reverse proxy: route + policies, no MCP
STOA_GATEWAY_MODE=shadow              → Passive: observe traffic, generate UAC YAML
```

## Taches

### 1. Mode Module Structure
Creer `stoa-gateway/src/mode/`:
```
mode/
├── mod.rs          # ModeConfig enum + factory
├── edge_mcp.rs     # Refactor: extraire le comportement actuel de main.rs
├── sidecar.rs      # Auth + rate limit + metrics endpoints
├── proxy.rs        # HTTP reverse proxy + policies
└── shadow.rs       # Passive observation + UAC generation
```

### 2. ModeConfig enum (`mode/mod.rs`)
```rust
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum GatewayMode {
    #[default]
    EdgeMcp,
    Sidecar,
    Proxy,
    Shadow,
}

impl GatewayMode {
    pub fn from_env() -> Self {
        std::env::var("STOA_GATEWAY_MODE")
            .ok()
            .and_then(|s| serde_json::from_str(&format!("\"{}\"", s)).ok())
            .unwrap_or_default()
    }
}
```

### 3. EdgeMcp mode (`mode/edge_mcp.rs`)
- Extraire le code actuel de `main.rs` dans une fonction `pub async fn start(config: &AppConfig) -> Result<()>`
- C'est le mode par defaut, doit etre 100% backward compatible
- Inclut: SSE transport, MCP protocol, auth, tools, metering, OPA

### 4. Sidecar mode (`mode/sidecar.rs`)
- Lightweight: pas de MCP protocol, pas de tools
- Endpoints: `/auth/verify` (ext_authz compatible), `/metrics`, `/health`
- Auth: JWT validation, scope checking via OPA
- Rate limiting: per-client token bucket
- Response format compatible ext_authz (200 = allow, 403 = deny)

### 5. Proxy mode (`mode/proxy.rs`)
- HTTP reverse proxy via `hyper` (deja dans les deps)
- Route config via env ou fichier: `STOA_PROXY_UPSTREAM=http://backend:8080`
- Apply policies: auth, rate limit, request transform
- No MCP, no tools — classic API gateway behavior
- Headers forwarding, path rewriting

### 6. Shadow mode (`mode/shadow.rs`) — KILLER FEATURE
- Passive traffic observation (read-only tap)
- Auto-generate UAC YAML from observed API patterns:
  - Detect endpoints (URL patterns)
  - Detect HTTP methods
  - Detect request/response schemas (sample-based)
  - Detect auth patterns (Bearer, API key, etc.)
- Output: `stoa-shadow-discovery.yaml` (importable into STOA)
- Zero impact on existing traffic

Creer `stoa-gateway/src/shadow/`:
```
shadow/
├── discovery.rs       # Traffic analysis engine
└── uac_generator.rs   # YAML output
```

### 7. Anti-Zombie Detection (`stoa-gateway/src/governance/zombie.rs`)
- Tool registration TTL: 10 minutes
- Tools must re-attest periodically
- Expired tools removed from `tools/list`
- Background task checking TTL every 30s

### 8. Wire into main.rs
```rust
match GatewayMode::from_env() {
    GatewayMode::EdgeMcp => mode::edge_mcp::start(&config).await?,
    GatewayMode::Sidecar => mode::sidecar::start(&config).await?,
    GatewayMode::Proxy => mode::proxy::start(&config).await?,
    GatewayMode::Shadow => mode::shadow::start(&config).await?,
}
```

### 9. Tests
- Unit: mode parsing from env var
- Unit: shadow discovery pattern detection
- Unit: anti-zombie TTL expiration
- Integration: each mode starts and responds to health check

### 10. Verifier
- `cargo test` vert
- `cargo clippy -- -D warnings` propre
- `cargo fmt --check` propre
- `STOA_GATEWAY_MODE=edge_mcp cargo run` fonctionne (backward compatible)

## DoD
- [ ] `STOA_GATEWAY_MODE=edge_mcp` fonctionne (default, backward compatible)
- [ ] `STOA_GATEWAY_MODE=sidecar` expose auth-only endpoints
- [ ] `STOA_GATEWAY_MODE=proxy` route HTTP sans MCP
- [ ] `STOA_GATEWAY_MODE=shadow` demarre en mode passif
- [ ] Anti-zombie: tool expire disparait de tools/list
- [ ] `cargo test` + `cargo clippy` clean
- [ ] Commit: `feat(gateway): 4-mode architecture with shadow discovery (CAB-1105)`

## Contraintes
- EdgeMcp = 100% backward compatible (rien ne casse)
- Shadow = read-only (zero ecriture vers un backend)
- Single binary — mode selectionne a runtime, pas a la compilation
- Feature flags: `STOA_SHADOW_ENABLED`, `STOA_ZOMBIE_TTL_SECONDS`
- Ne PAS push
