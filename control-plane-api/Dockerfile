FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Environment variables with defaults
# Override at runtime via docker run -e or Kubernetes ConfigMap/Secrets

# Core Configuration
ENV BASE_DOMAIN=apim.cab-i.com \
    ENVIRONMENT=production \
    DEBUG=false \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json

# Keycloak Authentication
ENV KEYCLOAK_URL=https://auth.apim.cab-i.com \
    KEYCLOAK_REALM=apim \
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
ENV KAFKA_BOOTSTRAP_SERVERS=redpanda.apim-system.svc.cluster.local:9092 \
    KAFKA_SECURITY_PROTOCOL=PLAINTEXT \
    KAFKA_SASL_MECHANISM="" \
    KAFKA_SASL_USERNAME="" \
    KAFKA_SASL_PASSWORD=""

# AWX Automation
ENV AWX_URL=https://awx.apim.cab-i.com \
    AWX_TOKEN="" \
    AWX_VERIFY_SSL=true

# API Gateway
ENV GATEWAY_URL=https://gateway.apim.cab-i.com \
    GATEWAY_ADMIN_USER=Administrator \
    GATEWAY_ADMIN_PASSWORD=""

# CORS
ENV CORS_ORIGINS=https://devops.apim.cab-i.com,http://localhost:3000,http://localhost:5173

# Rate Limiting
ENV RATE_LIMIT_REQUESTS=100 \
    RATE_LIMIT_WINDOW_SECONDS=60

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
