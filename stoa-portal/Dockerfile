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
ARG VITE_APP_TITLE="STOA Developer Portal"
ARG VITE_APP_VERSION=1.0.0

# MCP Gateway Configuration
ARG VITE_MCP_URL=https://mcp.stoa.cab-i.com
ARG VITE_MCP_TIMEOUT=30000

# API Configuration
ARG VITE_API_URL=https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0
ARG VITE_API_TIMEOUT=30000

# Keycloak Authentication - DIFFERENT CLIENT from Console
ARG VITE_KEYCLOAK_URL=https://auth.stoa.cab-i.com
ARG VITE_KEYCLOAK_REALM=stoa
ARG VITE_KEYCLOAK_CLIENT_ID=stoa-portal

# External Services
ARG VITE_CONSOLE_URL=https://console.stoa.cab-i.com
ARG VITE_DOCS_URL=https://docs.stoa.cab-i.com

# Feature Flags
ARG VITE_ENABLE_MCP_TOOLS=true
ARG VITE_ENABLE_SUBSCRIPTIONS=true
ARG VITE_ENABLE_API_CATALOG=false
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

# Production stage
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built app
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
