# syntax=docker/dockerfile:1

# ==============================================================================
# STOA Gateway — Optimized Multi-Stage Build with cargo-chef
# ==============================================================================
#
# cargo-chef splits the build into 3 stages:
#   1. planner  — analyse deps from Cargo.toml/Cargo.lock
#   2. builder  — build deps (cached), then build app
#   3. runtime  — minimal image with just the binary
#
# Dependency layer is rebuilt only when Cargo.toml or Cargo.lock changes.
# Source-only changes skip dep compilation entirely.
#
# Build:
#   docker buildx build --platform linux/amd64 -t stoa-gateway:latest .
#   (add linux/arm64 for local Mac dev if needed)
# ==============================================================================

# --- Stage 1: Plan dependencies -----------------------------------------------
FROM rust:1.88-bookworm AS planner
RUN cargo install cargo-chef --locked
WORKDIR /app
COPY Cargo.toml Cargo.lock* ./
COPY src ./src
RUN cargo chef prepare --recipe-path recipe.json

# --- Stage 2: Build -----------------------------------------------------------
FROM rust:1.88-bookworm AS builder

# Install cargo-chef and build deps
RUN cargo install cargo-chef --locked && \
    apt-get update && apt-get install -y \
      pkg-config \
      libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cook dependencies (cached unless Cargo.toml/Cargo.lock change)
COPY --from=planner /app/recipe.json recipe.json
RUN cargo chef cook --release --recipe-path recipe.json

# Build the actual application (only this layer rebuilds on src changes)
COPY Cargo.toml Cargo.lock* ./
COPY src ./src
RUN cargo build --release

# --- Stage 3: Runtime (minimal) -----------------------------------------------
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y \
      ca-certificates \
      libssl3 \
      curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r stoa && useradd -r -g stoa stoa

WORKDIR /app

COPY --from=builder /app/target/release/stoa-gateway /app/stoa-gateway
RUN chown -R stoa:stoa /app

USER stoa
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENV STOA_HOST=0.0.0.0 \
    STOA_PORT=8080 \
    STOA_LOG_LEVEL=info \
    STOA_LOG_FORMAT=json

ENTRYPOINT ["/app/stoa-gateway"]
