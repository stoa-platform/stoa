# syntax=docker/dockerfile:1
# STOA Control Plane - Multi-stage build

# ─────────────────────────────────────────────────────────────────
# Builder stage - install dependencies
# ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir poetry==1.8.3

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Export to requirements.txt (no dev dependencies)
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes --without dev

# ─────────────────────────────────────────────────────────────────
# Production stage
# ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from builder and install
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create non-root user
RUN useradd -m -u 1000 stoa && chown -R stoa:stoa /app
USER stoa

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run with uvicorn
EXPOSE 8080
ENV PYTHONPATH=/app/src

CMD ["uvicorn", "control_plane.main:app", "--host", "0.0.0.0", "--port", "8080"]
