/**
 * Application Configuration
 *
 * All settings can be configured via environment variables at build time (Vite).
 * Use VITE_* prefix for all environment variables.
 *
 * Environment Variables:
 * ----------------------
 * Core:
 * - VITE_BASE_DOMAIN: Base domain for all services (default: gostoa.dev)
 * - VITE_ENVIRONMENT: Environment name (dev, staging, production)
 * - VITE_APP_TITLE: Application title
 *
 * API:
 * - VITE_API_URL: Control Plane API base URL
 * - VITE_API_DOCS_URL: API documentation URL
 *
 * Authentication (Keycloak):
 * - VITE_KEYCLOAK_URL: Keycloak base URL
 * - VITE_KEYCLOAK_REALM: Keycloak realm name
 * - VITE_KEYCLOAK_CLIENT_ID: Keycloak client ID for this app
 *
 * External Services:
 * - VITE_GATEWAY_URL: API Gateway URL
 * - VITE_AWX_URL: AWX/Ansible Tower URL
 * - VITE_PORTAL_URL: Developer Portal URL
 * - VITE_GITLAB_URL: GitLab URL for repository links
 *
 * Feature Flags:
 * - VITE_ENABLE_MONITORING: Enable monitoring features (default: true)
 * - VITE_ENABLE_GITOPS: Enable GitOps features (default: true)
 * - VITE_ENABLE_DEBUG: Enable debug mode (default: false)
 */

// Base domain - used to construct default URLs for all services
const BASE_DOMAIN = import.meta.env.VITE_BASE_DOMAIN || 'gostoa.dev';

// Environment detection
const ENVIRONMENT = import.meta.env.VITE_ENVIRONMENT || 'production';
const IS_DEV = ENVIRONMENT === 'dev' || ENVIRONMENT === 'development';

export const config = {
  // Application metadata
  app: {
    title: import.meta.env.VITE_APP_TITLE || 'STOA Control Plane',
    version: import.meta.env.VITE_APP_VERSION || '2.0.0',
    environment: ENVIRONMENT,
    isDev: IS_DEV,
    baseDomain: BASE_DOMAIN,
  },

  // API Configuration
  // Direct connection to Control-Plane-API backend
  api: {
    baseUrl: import.meta.env.VITE_API_URL || `https://api.${BASE_DOMAIN}`,
    docsUrl: import.meta.env.VITE_API_DOCS_URL || `https://api.${BASE_DOMAIN}/docs`,
    timeout: Number(import.meta.env.VITE_API_TIMEOUT) || 30000,
  },

  // Keycloak Configuration
  keycloak: {
    url: import.meta.env.VITE_KEYCLOAK_URL || `https://auth.${BASE_DOMAIN}`,
    realm: import.meta.env.VITE_KEYCLOAK_REALM || 'stoa',
    clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'control-plane-ui',
    get authority() {
      return `${this.url}/realms/${this.realm}`;
    },
  },

  // External Services
  services: {
    gateway: {
      url: import.meta.env.VITE_GATEWAY_URL || `https://gateway.${BASE_DOMAIN}`,
      get consoleUrl() {
        return `${this.url}/apigatewayui/`;
      },
    },
    mcpGateway: {
      url: import.meta.env.VITE_MCP_GATEWAY_URL || `https://mcp.${BASE_DOMAIN}`,
    },
    awx: {
      url: import.meta.env.VITE_AWX_URL || `https://awx.${BASE_DOMAIN}`,
      getJobUrl(jobId: string | number) {
        return `${this.url}/#/jobs/playbook/${jobId}`;
      },
    },
    portal: {
      url: import.meta.env.VITE_PORTAL_URL || `https://portal.${BASE_DOMAIN}`,
    },
    gitlab: {
      url: import.meta.env.VITE_GITLAB_URL || 'https://gitlab.com',
      getProjectUrl(projectId: string) {
        return `${this.url}/projects/${projectId}`;
      },
      getRepoUrl(projectPath: string) {
        return `${this.url}/${projectPath}`;
      },
    },
    // Observability services (CAB-654)
    argocd: {
      url: import.meta.env.VITE_ARGOCD_URL || `https://argocd.${BASE_DOMAIN}`,
      getAppUrl(appName: string) {
        return `${this.url}/applications/${appName}`;
      },
    },
    grafana: {
      url: import.meta.env.VITE_GRAFANA_URL || `https://grafana.${BASE_DOMAIN}`,
    },
    prometheus: {
      url: import.meta.env.VITE_PROMETHEUS_URL || `https://prometheus.${BASE_DOMAIN}`,
    },
    logs: {
      url: import.meta.env.VITE_LOGS_URL || `https://grafana.${BASE_DOMAIN}/explore`,
    },
  },

  // Feature Flags
  features: {
    enableMonitoring: import.meta.env.VITE_ENABLE_MONITORING !== 'false',
    enableGitOps: import.meta.env.VITE_ENABLE_GITOPS !== 'false',
    enableDebug: import.meta.env.VITE_ENABLE_DEBUG === 'true',
    enableApplications: import.meta.env.VITE_ENABLE_APPLICATIONS !== 'false',
    enableAITools: import.meta.env.VITE_ENABLE_AI_TOOLS !== 'false',
  },

  // UI Configuration
  ui: {
    itemsPerPage: Number(import.meta.env.VITE_ITEMS_PER_PAGE) || 20,
    refreshInterval: Number(import.meta.env.VITE_REFRESH_INTERVAL) || 30000,
    dateFormat: import.meta.env.VITE_DATE_FORMAT || 'YYYY-MM-DD HH:mm:ss',
  },
};

// Type for external links used in Quick Links section
export interface ExternalLink {
  name: string;
  url: string;
  description?: string;
}

// Quick links for the dashboard
export const quickLinks: ExternalLink[] = [
  {
    name: 'API Documentation',
    url: config.api.docsUrl,
    description: 'OpenAPI/Swagger documentation',
  },
  {
    name: 'Gateway Console',
    url: config.services.gateway.consoleUrl,
    description: 'webMethods API Gateway admin console',
  },
  {
    name: 'AWX Automation',
    url: config.services.awx.url,
    description: 'Ansible Tower for deployments',
  },
];

export default config;
