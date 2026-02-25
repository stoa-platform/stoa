# Build stage
# NOTE: Build context must be repo root (not portal/)
# Use: docker build -f portal/Dockerfile .
FROM node:20-alpine AS builder

WORKDIR /app

# Copy shared package first (monorepo dependency)
COPY shared/package*.json ./shared/
RUN cd shared && npm ci --ignore-scripts

# Copy main package files
COPY portal/package*.json ./portal/

# Install dependencies
WORKDIR /app/portal
RUN npm ci

# Copy source files (tsconfig.base.json needed by tsconfig.json extends)
WORKDIR /app
COPY tsconfig.base.json ./
COPY shared/ ./shared/
COPY portal/ ./portal/

WORKDIR /app/portal

# Build arguments - Override with --build-arg during docker build
# Example: docker build --build-arg VITE_BASE_DOMAIN=staging.example.com .

# Core Configuration
ARG VITE_BASE_DOMAIN=gostoa.dev
ARG VITE_ENVIRONMENT=production
ARG VITE_APP_TITLE="STOA Developer Portal"
ARG VITE_APP_VERSION=1.0.0

# MCP Gateway Configuration
ARG VITE_MCP_URL=https://mcp.gostoa.dev
ARG VITE_MCP_TIMEOUT=30000

# API Configuration (direct connection to Control-Plane-API)
ARG VITE_API_URL=https://api.gostoa.dev
ARG VITE_API_TIMEOUT=30000

# Keycloak Authentication - DIFFERENT CLIENT from Console
ARG VITE_KEYCLOAK_URL=https://auth.gostoa.dev
ARG VITE_KEYCLOAK_REALM=stoa
ARG VITE_KEYCLOAK_CLIENT_ID=stoa-portal

# External Services
ARG VITE_CONSOLE_URL=https://console.gostoa.dev
ARG VITE_DOCS_URL=https://docs.gostoa.dev

# Feature Flags
ARG VITE_ENABLE_MCP_TOOLS=true
ARG VITE_ENABLE_SUBSCRIPTIONS=true
ARG VITE_ENABLE_API_CATALOG=true
ARG VITE_ENABLE_DEBUG=false

# UI Settings
ARG VITE_ITEMS_PER_PAGE=20
ARG VITE_REFRESH_INTERVAL=30000

# Set environment variables from build args
ENV VITE_BASE_DOMAIN=$VITE_BASE_DOMAIN \
    VITE_ENVIRONMENT=$VITE_ENVIRONMENT \
    VITE_APP_TITLE=$VITE_APP_TITLE \
    VITE_APP_VERSION=$VITE_APP_VERSION \
    VITE_MCP_URL=$VITE_MCP_URL \
    VITE_MCP_TIMEOUT=$VITE_MCP_TIMEOUT \
    VITE_API_URL=$VITE_API_URL \
    VITE_API_TIMEOUT=$VITE_API_TIMEOUT \
    VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL \
    VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM \
    VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID \
    VITE_CONSOLE_URL=$VITE_CONSOLE_URL \
    VITE_DOCS_URL=$VITE_DOCS_URL \
    VITE_ENABLE_MCP_TOOLS=$VITE_ENABLE_MCP_TOOLS \
    VITE_ENABLE_SUBSCRIPTIONS=$VITE_ENABLE_SUBSCRIPTIONS \
    VITE_ENABLE_API_CATALOG=$VITE_ENABLE_API_CATALOG \
    VITE_ENABLE_DEBUG=$VITE_ENABLE_DEBUG \
    VITE_ITEMS_PER_PAGE=$VITE_ITEMS_PER_PAGE \
    VITE_REFRESH_INTERVAL=$VITE_REFRESH_INTERVAL

RUN npm run build

# Production stage - Use nginx-unprivileged for Kubernetes compatibility
FROM nginxinc/nginx-unprivileged:alpine

# Default API backend (overridden by K8s env var)
ENV API_BACKEND_URL=http://control-plane-api:8000

# Copy entrypoint scripts (DNS resolver extraction + envsubst with explicit var filter)
COPY portal/docker-entrypoint.d/15-extract-dns-resolver.envsh /docker-entrypoint.d/15-extract-dns-resolver.envsh
COPY portal/docker-entrypoint.d/19-envsubst-custom.sh /docker-entrypoint.d/19-envsubst-custom.sh

# Copy nginx template to custom dir (NOT /etc/nginx/templates/ — avoids built-in envsubst)
COPY portal/nginx.conf.template /etc/nginx/custom-templates/default.conf.template

# Copy built app
COPY --from=builder /app/portal/dist /usr/share/nginx/html

# nginx-unprivileged listens on 8080
EXPOSE 8080

# nginx-unprivileged already runs as non-root user (nginx:101)
CMD ["nginx", "-g", "daemon off;"]
