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
