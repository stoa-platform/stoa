FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (snappy for Kafka compression)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsnappy-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security (UID 1000 for k8s runAsNonRoot compatibility)
RUN groupadd -r -g 1000 stoa && useradd -r -u 1000 -g stoa -d /app stoa

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade jaraco.context wheel && \
    rm -rf /usr/lib/python3/dist-packages/jaraco.context-*.dist-info \
           /usr/lib/python3/dist-packages/jaraco/context* \
           /usr/lib/python3/dist-packages/wheel-*.dist-info

# Copy source code
COPY src/ ./src/

# Copy alembic configuration and migrations
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Set ownership to non-root user
RUN chown -R stoa:stoa /app

# Environment variables with defaults
# Override at runtime via docker run -e or Kubernetes ConfigMap/Secrets

# Python optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Core Configuration
ENV BASE_DOMAIN=gostoa.dev \
    ENVIRONMENT=production \
    DEBUG=false \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json

# Keycloak Authentication
ENV KEYCLOAK_URL=https://auth.gostoa.dev \
    KEYCLOAK_REALM=stoa \
    KEYCLOAK_CLIENT_ID=control-plane-api \
    KEYCLOAK_CLIENT_SECRET="" \
    KEYCLOAK_VERIFY_SSL=true

# GitLab Integration
ENV GITLAB_URL=https://gitlab.com \
    GITLAB_TOKEN="" \
    GITLAB_PROJECT_ID="" \
    GITLAB_WEBHOOK_SECRET="" \
    GITLAB_DEFAULT_BRANCH=main

# Kafka/Redpanda
ENV KAFKA_BOOTSTRAP_SERVERS=redpanda.stoa-system.svc.cluster.local:9092 \
    KAFKA_SECURITY_PROTOCOL=PLAINTEXT \
    KAFKA_SASL_MECHANISM="" \
    KAFKA_SASL_USERNAME="" \
    KAFKA_SASL_PASSWORD=""

# API Gateway
ENV GATEWAY_URL=https://gateway.gostoa.dev \
    GATEWAY_ADMIN_USER=Administrator \
    GATEWAY_ADMIN_PASSWORD=""

# CORS
ENV CORS_ORIGINS=https://console.gostoa.dev,http://localhost:3000,http://localhost:5173

# Rate Limiting
ENV RATE_LIMIT_REQUESTS=100 \
    RATE_LIMIT_WINDOW_SECONDS=60

# Expose port
EXPOSE 8000

# Switch to non-root user (numeric UID required by k8s runAsNonRoot)
USER 1000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
