# STOA MCP Gateway - Production Dockerfile
# Multi-stage build for minimal image size

FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for better caching
COPY pyproject.toml ./

# Install dependencies
RUN pip install --no-cache-dir build && \
    pip wheel --no-cache-dir --wheel-dir /app/wheels .

# Production image
FROM python:3.11-slim as production

WORKDIR /app

# Create non-root user
RUN groupadd -r stoa && useradd -r -g stoa stoa

# Copy wheels from builder
COPY --from=builder /app/wheels /app/wheels

# Install dependencies from wheels
RUN pip install --no-cache-dir /app/wheels/*.whl && \
    rm -rf /app/wheels

# Copy application code
COPY src/ ./src/

# Set ownership
RUN chown -R stoa:stoa /app

USER stoa

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()"

# Run the application
CMD ["python", "-m", "src.main"]
