---
description: Rust code style for stoa-gateway
globs: "stoa-gateway/**/*.rs"
---

# Rust Code Style

## Tools: cargo fmt + clippy

## Formatting
- `cargo fmt` — standard Rust formatting
- Run before commit

## Linting
- `cargo clippy` — lint with warnings as errors
- Fix all clippy warnings before PR

## CI Exact Commands

```bash
# Standard CI (reusable-rust-ci.yml)
RUSTFLAGS=-Dwarnings cargo clippy --all-targets --all-features -- -D warnings
cargo fmt --check
cargo test --all-features

# Security SAST (security-scan.yml) — stricter
cargo clippy --all-targets --all-features -- \
  -W warnings \
  -D clippy::todo \
  -D clippy::unimplemented \
  -D clippy::dbg_macro \
  -W clippy::unwrap_used \
  -W clippy::expect_used \
  -W clippy::panic
```

**Zero tolerance** — any warning = CI failure. Never use `#[allow(...)]` without justification.

## System Dependencies

`rdkafka` crate requires system libs for Kafka support:

```bash
# macOS (local dev)
brew install librdkafka

# Ubuntu/CI (reusable-rust-ci.yml installs these)
sudo apt-get install -y libcurl4-openssl-dev libsasl2-dev cmake
```

Cargo feature: `kafka = ["rdkafka"]` — optional, enabled via `--all-features` in CI.

## Build & Test
```bash
cargo check            # Fast compile check
cargo test             # Run tests (default features)
cargo test --all-features  # Run tests (incl. kafka)
cargo clippy           # Lint
cargo fmt --check      # Format check
```

## Conventions
- Framework: Tokio + axum
- Error handling: anyhow for app, thiserror for libraries
- Async runtime: Tokio
- Stable toolchain
- Prefer `?` operator over explicit match for error propagation

## Clippy Gotchas (stoa-gateway specific)

| Issue | Wrong | Right |
|-------|-------|-------|
| `Action` implements `Copy` | `self.action.clone()` | `self.action` (no clone needed) |
| Private modules | `metering::events::X` | Use re-exports from `metering` |
| axum State type mismatch | `State<Arc<ModeService>>` when router state is `AppState` | Use closures that capture the service |
| Nested if (clippy 1.93+) | `if a { if b { ... } }` | `if a && b { ... }` |
| Redundant clone | `.clone()` on `Copy` types | Remove the `.clone()` |
| `todo!()` / `unimplemented!()` | Left in code | Blocked by SAST `-D clippy::todo` |
| `dbg!()` | Left in code | Blocked by SAST `-D clippy::dbg_macro` |

## Error Handling Patterns

```rust
// App-level errors (handlers, main) — use anyhow
use anyhow::{Context, Result};

fn load_config() -> Result<Config> {
    let data = std::fs::read("config.toml")
        .context("failed to read config file")?;
    // ...
}

// Library errors (traits, shared types) — use thiserror
use thiserror::Error;

#[derive(Error, Debug)]
pub enum GatewayError {
    #[error("tool not found: {0}")]
    ToolNotFound(String),
    #[error("auth failed: {0}")]
    AuthFailed(#[from] AuthError),
}
```

## Test Patterns

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_handler_returns_ok() {
        // Arrange
        let state = /* ... */;
        // Act
        let response = handler(state).await;
        // Assert
        assert_eq!(response.status(), StatusCode::OK);
    }
}
```

- Tests live inline (`#[cfg(test)] mod tests`) in the same file
- Use `#[tokio::test]` for async tests
- Mock with `mockall` crate or test HTTP servers
- Run: `cargo test --all-features`
