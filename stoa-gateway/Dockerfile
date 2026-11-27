# syntax=docker/dockerfile:1

# ==============================================================================
# STOA Gateway — Optimized Multi-Stage Build with cargo-chef
# ==============================================================================
#
# cargo-chef splits the build into 3 stages:
#   1. planner  — analyse deps from Cargo.toml/Cargo.lock
#   2. builder  — build deps (cached), then build app
#   3. runtime-debian — Debian slim with a shell and curl, for the local
#                       compose files and e2e tests whose healthchecks run
#                       curl inside the container (`target: runtime-debian`)
#   4. runtime  — distroless, no shell or package manager: default target,
#                 the image CI publishes and scans
#
# Dependency layer is rebuilt only when Cargo.toml or Cargo.lock changes.
# Source-only changes skip dep compilation entirely.
#
# Build:
#   docker buildx build --platform linux/amd64 -t stoa-gateway:latest .
#   (add linux/arm64 for local Mac dev if needed)
# ==============================================================================

# --- Stage 1: Plan dependencies -----------------------------------------------
FROM rust:1.100-bookworm@sha256:ade39a710ef85f3506cffcfec3e8a24ba090badef1dff2fb798f71d878833fea AS planner
RUN cargo install cargo-chef --locked
WORKDIR /app
COPY Cargo.toml Cargo.lock* ./
COPY src ./src
COPY policies ./policies
COPY benches ./benches
COPY build.rs ./
COPY proto ./proto
RUN cargo chef prepare --recipe-path recipe.json

# --- Stage 2: Build -----------------------------------------------------------
FROM rust:1.100-bookworm@sha256:ade39a710ef85f3506cffcfec3e8a24ba090badef1dff2fb798f71d878833fea AS builder

# Feature flags for community/enterprise image split (ADR-041 Phase 3)
#   empty   = community (default — lean image, no optional deps)
#   kafka   = Kafka metering (requires cmake for rdkafka)
#   k8s     = K8s CRD watcher (kube, k8s-openapi)
#   pingora = Pingora connection pool (pingora-core, needs cmake)
# Example: docker build --build-arg FEATURES="kafka,pingora" .
ARG FEATURES=""
# Companion profile: disable Cargo defaults explicitly, including future defaults.
ARG NO_DEFAULT_FEATURES=false

# Install cargo-chef and build deps
RUN cargo install cargo-chef --locked && \
    apt-get update && apt-get install -y \
      pkg-config \
      libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Conditionally install cmake + libs for features that need it:
# - kafka: rdkafka needs cmake + libsasl2
# - pingora: BoringSSL needs cmake + Go (for build)
RUN if echo "${FEATURES}" | grep -qE "kafka|pingora"; then \
      apt-get update && apt-get install -y cmake libsasl2-dev libcurl4-openssl-dev \
      && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app

# Cook dependencies (cached unless Cargo.toml/Cargo.lock change)
COPY --from=planner /app/recipe.json recipe.json
RUN if [ "${NO_DEFAULT_FEATURES}" = true ]; then set -- --no-default-features; else set --; fi && \
    cargo chef cook --locked --release --features "${FEATURES}" "$@" --recipe-path recipe.json

# Cache-bust: ensures source changes always trigger recompilation
# (GHA Docker layer cache can otherwise serve stale compiled artifacts)
ARG CACHEBUST=unknown
RUN echo "Build revision: ${CACHEBUST}"

# Build the actual application (only this layer rebuilds on src changes)
COPY Cargo.toml Cargo.lock* ./
COPY src ./src
COPY policies ./policies
COPY benches ./benches
COPY build.rs ./
COPY proto ./proto
RUN if [ "${NO_DEFAULT_FEATURES}" = true ]; then set -- --no-default-features; else set --; fi && \
    cargo build --locked --release --features "${FEATURES}" "$@" && strip target/release/stoa-gateway

# --- Stage 3: Debian runtime (local compose and e2e only) ----------------------
# Not published: CI builds the default target below. Kept for the compose
# files and e2e tests that run curl inside the container.
# The Bookworm-built binary uses compatible glibc/OpenSSL ABIs on Trixie.
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS runtime-debian

# Preserve the project distribution notices in the runtime image.
COPY LICENSE NOTICE /usr/share/licenses/stoa/

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
      ca-certificates \
      libssl3t64 \
      curl \
      zlib1g \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' zlib1g)" ge \
         '1:1.3.dfsg+really1.3.1-1+deb13u1' \
    && rm -rf /var/lib/apt/lists/*

# UID 1000 for k8s runAsNonRoot compatibility
RUN groupadd -r -g 1000 stoa && useradd -r -u 1000 -g stoa -d /app stoa

WORKDIR /app

COPY --from=builder /app/target/release/stoa-gateway /app/stoa-gateway
RUN chown -R stoa:stoa /app \
    && install -d -m 0700 -o stoa -g stoa /tmp/stoa-poc-floors

USER 1000
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENV STOA_HOST=0.0.0.0 \
    STOA_PORT=8080 \
    STOA_LOG_LEVEL=info \
    STOA_LOG_FORMAT=json

ENTRYPOINT ["/app/stoa-gateway"]

# --- Stage 4: Runtime (default target, published and scanned) ------------------
# Distroless: glibc, libgcc, libstdc++, OpenSSL, zlib and CA certificates, no
# shell, no package manager, no curl. The Debian stage above carried curl, its
# Kerberos/LDAP/SASL libraries, util-linux, perl and tar for a Docker
# HEALTHCHECK that Kubernetes ignores: the Deployment probes /health over HTTP.
FROM gcr.io/distroless/cc-debian13@sha256:e8343d4a7da8bb210df0c3ea29de38bbadbba6c773bed0cd8bde506fca3a5c44 AS runtime

COPY LICENSE NOTICE /usr/share/licenses/stoa/

WORKDIR /app

# Owned by root: the runtime user can execute the binary, not replace it.
COPY --from=builder /app/target/release/stoa-gateway /app/stoa-gateway

# Numeric on purpose: the base has no passwd entry for 1000, and k8s
# runAsNonRoot checks the number. The group is explicit so the process does
# not run with gid 0.
USER 1000:1000
EXPOSE 8080

ENV STOA_HOST=0.0.0.0 \
    STOA_PORT=8080 \
    STOA_LOG_LEVEL=info \
    STOA_LOG_FORMAT=json

ENTRYPOINT ["/app/stoa-gateway"]
