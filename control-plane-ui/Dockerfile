# Build stage
# NOTE: Build context must be repo root (not control-plane-ui/)
# Use: docker build -f control-plane-ui/Dockerfile .
FROM node:20-alpine AS builder

WORKDIR /app

# Copy shared package first (monorepo dependency)
COPY shared/package*.json ./shared/
RUN cd shared && npm ci --ignore-scripts

# Copy main package files
COPY control-plane-ui/package*.json ./control-plane-ui/

# Install dependencies
WORKDIR /app/control-plane-ui
RUN npm ci

# Copy source files
WORKDIR /app
COPY shared/ ./shared/
COPY control-plane-ui/ ./control-plane-ui/

WORKDIR /app/control-plane-ui

# Build arguments - Override with --build-arg during docker build
# Example: docker build --build-arg VITE_BASE_DOMAIN=staging.example.com .

# Core Configuration
ARG VITE_BASE_DOMAIN=stoa.cab-i.com
ARG VITE_ENVIRONMENT=production
ARG VITE_APP_TITLE="STOA Control Plane"
ARG VITE_APP_VERSION=2.0.0

# API Configuration (direct connection to Control-Plane-API)
ARG VITE_API_URL=https://api.stoa.cab-i.com
ARG VITE_API_TIMEOUT=30000

# Keycloak Authentication
ARG VITE_KEYCLOAK_URL=https://auth.stoa.cab-i.com
ARG VITE_KEYCLOAK_REALM=stoa
ARG VITE_KEYCLOAK_CLIENT_ID=control-plane-ui

# External Services
ARG VITE_GATEWAY_URL=https://gateway.stoa.cab-i.com
ARG VITE_AWX_URL=https://awx.stoa.cab-i.com
ARG VITE_PORTAL_URL=https://portal.stoa.cab-i.com
ARG VITE_GITLAB_URL=https://gitlab.com

# Feature Flags
ARG VITE_ENABLE_MONITORING=true
ARG VITE_ENABLE_GITOPS=true
ARG VITE_ENABLE_DEBUG=false
ARG VITE_ENABLE_APPLICATIONS=true
ARG VITE_ENABLE_AI_TOOLS=true

# MCP Gateway
ARG VITE_MCP_GATEWAY_URL=https://mcp.stoa.cab-i.com

# UI Settings
ARG VITE_ITEMS_PER_PAGE=20
ARG VITE_REFRESH_INTERVAL=30000

# Set environment variables from build args
ENV VITE_BASE_DOMAIN=$VITE_BASE_DOMAIN \
    VITE_ENVIRONMENT=$VITE_ENVIRONMENT \
    VITE_APP_TITLE=$VITE_APP_TITLE \
    VITE_APP_VERSION=$VITE_APP_VERSION \
    VITE_API_URL=$VITE_API_URL \
    VITE_API_TIMEOUT=$VITE_API_TIMEOUT \
    VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL \
    VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM \
    VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID \
    VITE_GATEWAY_URL=$VITE_GATEWAY_URL \
    VITE_AWX_URL=$VITE_AWX_URL \
    VITE_PORTAL_URL=$VITE_PORTAL_URL \
    VITE_GITLAB_URL=$VITE_GITLAB_URL \
    VITE_ENABLE_MONITORING=$VITE_ENABLE_MONITORING \
    VITE_ENABLE_GITOPS=$VITE_ENABLE_GITOPS \
    VITE_ENABLE_DEBUG=$VITE_ENABLE_DEBUG \
    VITE_ENABLE_APPLICATIONS=$VITE_ENABLE_APPLICATIONS \
    VITE_ENABLE_AI_TOOLS=$VITE_ENABLE_AI_TOOLS \
    VITE_MCP_GATEWAY_URL=$VITE_MCP_GATEWAY_URL \
    VITE_ITEMS_PER_PAGE=$VITE_ITEMS_PER_PAGE \
    VITE_REFRESH_INTERVAL=$VITE_REFRESH_INTERVAL

RUN npm run build

# Production stage - Use nginx-unprivileged for security (non-root)
FROM nginxinc/nginx-unprivileged:alpine

# Default backend URLs (overridable via K8s env vars)
ENV API_BACKEND_URL=http://control-plane-api:8000 \
    LOGS_BACKEND_URL=http://opensearch-dashboards:5601 \
    GRAFANA_BACKEND_URL=http://grafana:3000

# Only substitute our custom vars (preserve nginx $uri, $host, etc.)
# IMPORTANT: Use \$ to escape — Docker expands ${VAR} in ENV even inside single quotes
ENV NGINX_ENVSUBST_FILTER="\${API_BACKEND_URL} \${LOGS_BACKEND_URL} \${GRAFANA_BACKEND_URL} \${DNS_RESOLVER}"

# Extract DNS resolver from /etc/resolv.conf at startup (before envsubst)
COPY control-plane-ui/docker-entrypoint.d/15-extract-dns-resolver.envsh /docker-entrypoint.d/15-extract-dns-resolver.envsh

# Copy nginx template (processed by built-in 20-envsubst-on-templates.sh at startup)
COPY control-plane-ui/nginx.conf.template /etc/nginx/templates/default.conf.template

# Copy built app
COPY --from=builder /app/control-plane-ui/dist /usr/share/nginx/html

# nginx-unprivileged listens on 8080
EXPOSE 8080

# nginx-unprivileged already runs as non-root user (nginx:101)
CMD ["nginx", "-g", "daemon off;"]
