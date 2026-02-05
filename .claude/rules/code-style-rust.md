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

## Build & Test
```bash
cargo check       # Fast compile check
cargo test        # Run tests
cargo clippy      # Lint
cargo fmt --check # Format check
```

## Conventions
- Framework: Tokio + axum
- Error handling: anyhow for app, thiserror for libraries
- Async runtime: Tokio
- Stable toolchain
