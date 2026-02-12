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
COPY benches ./benches
RUN cargo chef prepare --recipe-path recipe.json

# --- Stage 2: Build -----------------------------------------------------------
FROM rust:1.88-bookworm AS builder

# Feature flags for community/enterprise image split (ADR-041 Phase 3)
#   empty   = community (default — lean image, no optional deps)
#   kafka   = Kafka metering (requires cmake for rdkafka)
#   k8s     = K8s CRD watcher (kube, k8s-openapi)
#   otel    = OpenTelemetry tracing (placeholder)
# Example: docker build --build-arg FEATURES="kafka,k8s" .
ARG FEATURES=""

# Install cargo-chef and build deps
RUN cargo install cargo-chef --locked && \
    apt-get update && apt-get install -y \
      pkg-config \
      libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Conditionally install cmake + libs when kafka feature is enabled (rdkafka)
RUN if echo "${FEATURES}" | grep -q "kafka"; then \
      apt-get update && apt-get install -y cmake libsasl2-dev libcurl4-openssl-dev \
      && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app

# Cook dependencies (cached unless Cargo.toml/Cargo.lock change)
COPY --from=planner /app/recipe.json recipe.json
RUN cargo chef cook --release --features "${FEATURES}" --recipe-path recipe.json

# Cache-bust: ensures source changes always trigger recompilation
# (GHA Docker layer cache can otherwise serve stale compiled artifacts)
ARG CACHEBUST=unknown
RUN echo "Build revision: ${CACHEBUST}"

# Build the actual application (only this layer rebuilds on src changes)
COPY Cargo.toml Cargo.lock* ./
COPY src ./src
COPY benches ./benches
RUN cargo build --release --features "${FEATURES}" && strip target/release/stoa-gateway

# --- Stage 3: Runtime (minimal) -----------------------------------------------
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y \
      ca-certificates \
      libssl3 \
      curl \
    && rm -rf /var/lib/apt/lists/*

# UID 1000 for k8s runAsNonRoot compatibility
RUN groupadd -r -g 1000 stoa && useradd -r -u 1000 -g stoa -d /app stoa

WORKDIR /app

COPY --from=builder /app/target/release/stoa-gateway /app/stoa-gateway
RUN chown -R stoa:stoa /app

USER 1000
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENV STOA_HOST=0.0.0.0 \
    STOA_PORT=8080 \
    STOA_LOG_LEVEL=info \
    STOA_LOG_FORMAT=json

ENTRYPOINT ["/app/stoa-gateway"]
