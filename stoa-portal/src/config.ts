// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * STOA Developer Portal Configuration
 *
 * All settings can be configured via environment variables at build time (Vite).
 * Use VITE_* prefix for all environment variables.
 *
 * This portal uses a DIFFERENT Keycloak client (stoa-portal) from Console (control-plane-ui)
 * to allow different permission sets and redirect URIs.
 */

// Base domain - used to construct default URLs for all services
const BASE_DOMAIN = import.meta.env.VITE_BASE_DOMAIN || 'gostoa.dev';

// Environment detection
const ENVIRONMENT = import.meta.env.VITE_ENVIRONMENT || 'production';
const IS_DEV = ENVIRONMENT === 'dev' || ENVIRONMENT === 'development';

export const config = {
  // Application metadata
  app: {
    title: import.meta.env.VITE_APP_TITLE || 'STOA Developer Portal',
    version: import.meta.env.VITE_APP_VERSION || '1.0.0',
    environment: ENVIRONMENT,
    isDev: IS_DEV,
    baseDomain: BASE_DOMAIN,
  },

  // MCP Gateway Configuration (primary API for this portal)
  mcp: {
    baseUrl: import.meta.env.VITE_MCP_URL || `https://mcp.${BASE_DOMAIN}`,
    timeout: Number(import.meta.env.VITE_MCP_TIMEOUT) || 30000,
  },

  // Control Plane API (for subscriptions, profile)
  api: {
    baseUrl: import.meta.env.VITE_API_URL || `https://apis.${BASE_DOMAIN}/gateway/Control-Plane-API/2.0`,
    timeout: Number(import.meta.env.VITE_API_TIMEOUT) || 30000,
  },

  // Keycloak Configuration - DIFFERENT client from Console
  keycloak: {
    url: import.meta.env.VITE_KEYCLOAK_URL || `https://auth.${BASE_DOMAIN}`,
    realm: import.meta.env.VITE_KEYCLOAK_REALM || 'stoa',
    clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'stoa-portal', // Different from control-plane-ui
    get authority() {
      return `${this.url}/realms/${this.realm}`;
    },
  },

  // External Services (links)
  services: {
    console: {
      url: import.meta.env.VITE_CONSOLE_URL || `https://console.${BASE_DOMAIN}`,
    },
    docs: {
      url: import.meta.env.VITE_DOCS_URL || `https://docs.${BASE_DOMAIN}`,
    },
  },

  // Feature Flags
  features: {
    enableMCPTools: import.meta.env.VITE_ENABLE_MCP_TOOLS !== 'false',
    enableSubscriptions: import.meta.env.VITE_ENABLE_SUBSCRIPTIONS !== 'false',
    enableAPICatalog: import.meta.env.VITE_ENABLE_API_CATALOG === 'true', // Future feature
    enableDebug: import.meta.env.VITE_ENABLE_DEBUG === 'true',
  },

  // UI Configuration
  ui: {
    itemsPerPage: Number(import.meta.env.VITE_ITEMS_PER_PAGE) || 20,
    refreshInterval: Number(import.meta.env.VITE_REFRESH_INTERVAL) || 30000,
  },
};

export default config;
