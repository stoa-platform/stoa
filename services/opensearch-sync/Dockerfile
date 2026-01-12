# =============================================================================
# STOA Platform - OpenSearch Sync Service
# =============================================================================
# Multi-stage build for minimal image size
# =============================================================================

FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Production image
# =============================================================================
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1000 -g root stoa

# Copy virtual environment
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application
COPY sync_service.py .

# Set user
USER 1000

# Default command
ENTRYPOINT ["python", "sync_service.py"]
CMD ["--mode", "realtime"]

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python sync_service.py --mode health || exit 1

# Labels
LABEL org.opencontainers.image.title="STOA OpenSearch Sync Service" \
      org.opencontainers.image.description="Syncs PostgreSQL tools catalog to OpenSearch" \
      org.opencontainers.image.vendor="STOA Platform" \
      org.opencontainers.image.source="https://github.com/stoa-platform/stoa"
