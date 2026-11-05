# =============================================================================
# STOA Platform - Kafka Bridge Service
# =============================================================================
# HTTP to Kafka relay for gateway error snapshots (CAB-485)
# Supports webMethods, Kong, Traefik, and any HTTP-capable gateway
# =============================================================================

FROM python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893 as builder

WORKDIR /app

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Production image
# =============================================================================
FROM python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893

WORKDIR /app

# Upgrade system packages to fix CVEs in base image + create non-root user
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1000 -g root stoa

# Copy virtual environment
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application
COPY main.py .

# Set user
USER 1000

# Expose port
EXPOSE 8080

# Default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Labels
LABEL org.opencontainers.image.title="STOA Kafka Bridge" \
      org.opencontainers.image.description="HTTP to Kafka relay for gateway error snapshots" \
      org.opencontainers.image.vendor="STOA Platform" \
      org.opencontainers.image.source="https://github.com/stoa-platform/stoa"
