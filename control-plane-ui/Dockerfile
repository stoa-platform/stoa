# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY . .

# Build app - Environment variables for Vite build
# These are defaults; override with --build-arg during docker build
ARG VITE_BASE_DOMAIN=apim.cab-i.com
ARG VITE_API_URL=https://api.apim.cab-i.com
ARG VITE_KEYCLOAK_URL=https://auth.apim.cab-i.com
ARG VITE_KEYCLOAK_REALM=apim
ARG VITE_KEYCLOAK_CLIENT_ID=control-plane-ui

ENV VITE_BASE_DOMAIN=$VITE_BASE_DOMAIN
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL
ENV VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM
ENV VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID

RUN npm run build

# Production stage
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built app
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
