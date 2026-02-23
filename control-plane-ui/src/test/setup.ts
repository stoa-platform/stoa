import '@testing-library/jest-dom';
import { vi } from 'vitest';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

// Initialize i18n for tests with inline English resources
i18n.use(initReactI18next).init({
  lng: 'en',
  fallbackLng: 'en',
  ns: ['common'],
  defaultNS: 'common',
  initImmediate: false,
  interpolation: { escapeValue: false },
  resources: {
    en: {
      common: {
        nav: {
          overview: 'Overview',
          dashboard: 'Dashboard',
          operations: 'Operations',
          myUsage: 'My Usage',
          business: 'Business',
          catalog: 'Catalog',
          tenants: 'Tenants',
          apis: 'APIs',
          aiTools: 'AI Tools',
          externalMcpServers: 'External MCP Servers',
          applications: 'Applications',
          consumers: 'Consumers',
          saas: 'SaaS',
          backendApis: 'Backend APIs',
          apiKeys: 'API Keys',
          gateway: 'Gateway',
          status: 'Status',
          registry: 'Registry',
          modes: 'Modes',
          deployments: 'Deployments',
          drift: 'Drift',
          metrics: 'Metrics',
          federation: 'Federation',
          skills: 'Skills',
          insights: 'Insights',
          identity: 'Identity',
          apiMonitoring: 'API Monitoring',
          monitoring: 'Monitoring',
          errorSnapshots: 'Error Snapshots',
          executions: 'Executions',
          observability: 'Observability',
          logs: 'Logs',
          governance: 'Governance',
          shadowDiscovery: 'Shadow Discovery',
          tokenOptimizer: 'Token Optimizer',
          policies: 'Policies',
          auditLog: 'Audit Log',
          workflows: 'Workflows',
          audienceGovernance: 'Audience Governance',
          audience: 'Audience',
        },
        layout: {
          controlPlane: 'Control Plane',
          environment: 'Environment',
          tenant: 'Tenant',
          selectTenant: 'Select tenant',
          apiError: 'Cannot connect to the STOA API. Some features may be unavailable.',
        },
        commandPalette: {
          createNewApi: 'Create New API',
          createNewApiDesc: 'Add a new API definition',
          createNewTenant: 'Create New Tenant',
          createNewTenantDesc: 'Add a new tenant',
          logoutDesc: 'Sign out of your account',
          switchToLight: 'Switch to Light Mode',
          switchToDark: 'Switch to Dark Mode',
          currentlyIn: 'Currently in {{theme}} mode',
          navigateTo: 'Navigate to {{name}}',
          goTo: 'Go to {{name}}',
        },
        dashboard: {
          title: 'Dashboard',
          welcome: 'Welcome to STOA Control Plane',
          hello: 'Hello, {{name}}!',
          quickActions: {
            apis: 'APIs',
            apisDesc: 'Manage API definitions and deployments',
            aiTools: 'AI Tools',
            aiToolsDesc: 'Browse MCP tools catalog',
            applications: 'Applications',
            applicationsDesc: 'Manage consumer applications',
            deployments: 'Deployments',
            deploymentsDesc: 'View deployment history',
          },
          quickLinks: 'Quick Links',
          gettingStarted: 'Getting Started',
        },
        common: {
          loading: 'Loading...',
          search: 'Search...',
          logout: 'Logout',
          readOnly: 'Read-only',
          fullAccess: 'Full access',
        },
        login: {
          title: 'STOA Control Plane',
          subtitle: 'Multi-tenant API Management',
          button: 'Login with Keycloak',
        },
      },
    },
  },
});

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock navigator.clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
    readText: vi.fn().mockResolvedValue(''),
  },
});

// Mock ResizeObserver
(globalThis as Record<string, unknown>).ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));
