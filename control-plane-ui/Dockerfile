# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY . .

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

# Copy custom nginx config (nginx-unprivileged uses 8080 by default)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built app
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx-unprivileged listens on 8080
EXPOSE 8080

# nginx-unprivileged already runs as non-root user (nginx:101)
CMD ["nginx", "-g", "daemon off;"]
