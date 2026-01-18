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
const BASE_DOMAIN = import.meta.env.VITE_BASE_DOMAIN || 'stoa.cab-i.com';

// Environment detection
const ENVIRONMENT = import.meta.env.VITE_ENVIRONMENT || 'production';
const IS_DEV = ENVIRONMENT === 'dev' || ENVIRONMENT === 'development';

export const config = {
  // Base domain at root level for easy access
  baseDomain: BASE_DOMAIN,

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
  // Direct connection to Control-Plane-API backend
  api: {
    baseUrl: import.meta.env.VITE_API_URL || `https://api.${BASE_DOMAIN}`,
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

  // Portal Mode (production vs non-production)
  portalMode: (import.meta.env.VITE_PORTAL_MODE as 'production' | 'non-production') || 'production',

  // Feature Flags
  features: {
    enableMCPTools: import.meta.env.VITE_ENABLE_MCP_TOOLS !== 'false',
    enableSubscriptions: import.meta.env.VITE_ENABLE_SUBSCRIPTIONS !== 'false',
    enableAPICatalog: import.meta.env.VITE_ENABLE_API_CATALOG !== 'false', // Enabled by default
    enableApplications: import.meta.env.VITE_ENABLE_APPLICATIONS !== 'false', // Consumer apps
    enableAPITesting: import.meta.env.VITE_ENABLE_API_TESTING !== 'false', // Sandbox testing
    enableDebug: import.meta.env.VITE_ENABLE_DEBUG === 'true',
  },

  // API Testing Configuration
  testing: {
    // Available environments for this portal instance
    availableEnvironments: (import.meta.env.VITE_AVAILABLE_ENVIRONMENTS || 'prod').split(','),
    // Require confirmation before testing (for production portal)
    requireSandboxConfirmation: import.meta.env.VITE_REQUIRE_SANDBOX_CONFIRMATION === 'true',
  },

  // UI Configuration
  ui: {
    itemsPerPage: Number(import.meta.env.VITE_ITEMS_PER_PAGE) || 20,
    refreshInterval: Number(import.meta.env.VITE_REFRESH_INTERVAL) || 30000,
  },
};

export default config;
