# CAB-1018: Mock APIs for Central Bank Demo
# Multi-stage build for smaller image

FROM python:3.11-slim as builder

WORKDIR /app

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN useradd -r -u 1000 -g root stoa

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY src/ ./src/

# Set ownership
RUN chown -R 1000:root /app

# Switch to non-root user
USER 1000

# Expose port
EXPOSE 8090

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/health')" || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8090"]

# Labels
LABEL org.opencontainers.image.title="STOA Mock Backends" \
      org.opencontainers.image.description="Mock APIs for Central Bank Demo (CAB-1018)" \
      org.opencontainers.image.vendor="STOA Platform" \
      org.opencontainers.image.version="0.2.0"
