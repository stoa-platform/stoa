/**
 * STOA Developer Portal Configuration
 *
 * Config resolution order: runtime (container env) > build-time (Vite) > fallback.
 * This allows a single Docker image to be deployed to any environment.
 *
 * - Runtime: window.__STOA_RUNTIME__ (injected by 19-envsubst-custom.sh at container startup)
 * - Build-time: import.meta.env.VITE_* (baked by Vite, used for npm run dev)
 * - Fallback: hardcoded defaults (production URLs)
 *
 * This portal uses a DIFFERENT Keycloak client (stoa-portal) from Console (control-plane-ui)
 * to allow different permission sets and redirect URIs.
 */

// Runtime config injected by container entrypoint (19-envsubst-custom.sh).
const rt = (typeof window !== 'undefined' &&
  (window as unknown as Record<string, unknown>).__STOA_RUNTIME__) as
  | Record<string, string>
  | undefined;

/** Read a config value: runtime (container env) > build-time (Vite) > fallback */
const env = (key: string, fallback: string): string =>
  (rt && rt[key]) || import.meta.env[key] || fallback;

// Base domain - used to construct default URLs for all services
const BASE_DOMAIN = env('VITE_BASE_DOMAIN', 'gostoa.dev');

// Environment detection
const ENVIRONMENT = env('VITE_ENVIRONMENT', 'production');
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
    baseUrl: env('VITE_MCP_URL', `https://mcp.${BASE_DOMAIN}`),
    timeout: Number(import.meta.env.VITE_MCP_TIMEOUT) || 30000,
  },

  // Control Plane API (for subscriptions, profile)
  // Direct connection to Control-Plane-API backend
  api: {
    baseUrl: env('VITE_API_URL', `https://api.${BASE_DOMAIN}`),
    timeout: Number(import.meta.env.VITE_API_TIMEOUT) || 30000,
  },

  // Keycloak Configuration - DIFFERENT client from Console
  keycloak: {
    url: env('VITE_KEYCLOAK_URL', `https://auth.${BASE_DOMAIN}`),
    realm: env('VITE_KEYCLOAK_REALM', 'stoa'),
    clientId: env('VITE_KEYCLOAK_CLIENT_ID', 'stoa-portal'), // Different from control-plane-ui
    get authority() {
      return `${this.url}/realms/${this.realm}`;
    },
  },

  // External Services (links)
  services: {
    console: {
      url: env('VITE_CONSOLE_URL', `https://console.${BASE_DOMAIN}`),
    },
    docs: {
      url: env('VITE_DOCS_URL', `https://docs.${BASE_DOMAIN}`),
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
    enableGateways: import.meta.env.VITE_ENABLE_GATEWAYS !== 'false',
    enableI18n: import.meta.env.VITE_ENABLE_I18N !== 'false',
    enableMarketplace: import.meta.env.VITE_ENABLE_MARKETPLACE !== 'false',
    enableNotifications: import.meta.env.VITE_ENABLE_NOTIFICATIONS !== 'false',
    enableAuditLog: import.meta.env.VITE_ENABLE_AUDIT_LOG !== 'false',
    enableFavorites: import.meta.env.VITE_ENABLE_FAVORITES !== 'false',
    enableRateLimits: import.meta.env.VITE_ENABLE_RATE_LIMITS !== 'false',
    enableAPIComparison: import.meta.env.VITE_ENABLE_API_COMPARISON !== 'false',
  },

  // API Testing Configuration
  testing: {
    // Available environments for this portal instance
    availableEnvironments: (import.meta.env.VITE_AVAILABLE_ENVIRONMENTS || 'prod').split(','),
    // Require confirmation before testing (for production portal)
    requireSandboxConfirmation: import.meta.env.VITE_REQUIRE_SANDBOX_CONFIRMATION === 'true',
  },

  // Grafana Analytics (embedded dashboards, role-gated)
  grafana: {
    url: import.meta.env.VITE_GRAFANA_URL || '',
  },

  // UI Configuration
  ui: {
    itemsPerPage: Number(import.meta.env.VITE_ITEMS_PER_PAGE) || 20,
    refreshInterval: Number(import.meta.env.VITE_REFRESH_INTERVAL) || 30000,
  },
};

export default config;
