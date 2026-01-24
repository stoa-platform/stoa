# syntax=docker/dockerfile:1

# Multi-stage build for multi-arch support (AMD64 for EKS, ARM64 for Mac)
# Build with: docker buildx build --platform linux/amd64,linux/arm64 -t stoa-gateway:latest --push .

# ==============================================================================
# Stage 1: Build stage
# ==============================================================================
FROM rust:1.82-bookworm AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy manifests first for better caching
COPY Cargo.toml Cargo.lock* ./

# Create dummy main.rs to build dependencies
RUN mkdir -p src && \
    echo 'fn main() { println!("Dummy"); }' > src/main.rs

# Build dependencies only (this layer will be cached)
RUN cargo build --release && rm -rf src

# Copy actual source code
COPY src ./src

# Touch main.rs to invalidate the cache for the actual build
RUN touch src/main.rs

# Build the actual application
RUN cargo build --release

# ==============================================================================
# Stage 2: Runtime stage (minimal image)
# ==============================================================================
FROM debian:bookworm-slim AS runtime

# Install runtime dependencies (including curl for healthcheck)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r stoa && useradd -r -g stoa stoa

WORKDIR /app

# Copy the binary from the builder stage
COPY --from=builder /app/target/release/stoa-gateway /app/stoa-gateway

# Set ownership
RUN chown -R stoa:stoa /app

# Switch to non-root user
USER stoa

# Expose ports
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health/live || exit 1

# Set default environment variables
ENV HOST=0.0.0.0 \
    PORT=8080 \
    LOG_LEVEL=info \
    LOG_FORMAT=json \
    WEBMETHODS_HEALTH_CHECK_INTERVAL_SECS=5 \
    WEBMETHODS_HEALTH_CHECK_TIMEOUT_SECS=2

# Run the gateway
ENTRYPOINT ["/app/stoa-gateway"]
