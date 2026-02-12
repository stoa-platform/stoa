/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for App component — routing + auth integration
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock AuthContext with controllable state
const mockAuth = {
  user: null as any,
  isAuthenticated: false,
  isLoading: false,
  isReady: false,
  accessToken: null as string | null,
  hasPermission: vi.fn().mockReturnValue(true),
  hasAnyPermission: vi.fn().mockReturnValue(true),
  hasAllPermissions: vi.fn().mockReturnValue(true),
  hasRole: vi.fn().mockReturnValue(true),
  hasScope: vi.fn().mockReturnValue(true),
  login: vi.fn(),
  logout: vi.fn(),
  refreshPermissions: vi.fn(),
};

vi.mock('./contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuth: () => mockAuth,
}));

// Mock Layout
vi.mock('./components/layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="layout">{children}</div>
  ),
}));

// Mock common components
vi.mock('./components/common', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SkipLink: () => null,
}));

// Mock all lazy pages
vi.mock('./pages/Home', () => ({
  HomePage: () => <div data-testid="home-page">Home</div>,
}));

vi.mock('./pages/servers', () => ({
  MCPServersPage: () => <div data-testid="servers-page">Servers</div>,
  ServerDetailPage: () => <div data-testid="server-detail">Server Detail</div>,
}));

vi.mock('./pages/subscriptions/MySubscriptions', () => ({
  MySubscriptions: () => <div data-testid="subscriptions-page">Subscriptions</div>,
}));

vi.mock('./pages/apis', () => ({
  APICatalog: () => <div data-testid="api-catalog">APIs</div>,
  APIDetail: () => <div data-testid="api-detail">API Detail</div>,
  APITestingSandbox: () => <div data-testid="api-sandbox">Sandbox</div>,
}));

vi.mock('./pages/apps', () => ({
  MyApplications: () => <div data-testid="apps-page">Apps</div>,
  ApplicationDetail: () => <div data-testid="app-detail">App Detail</div>,
}));

vi.mock('./pages/contracts', () => ({
  ContractListPage: () => <div data-testid="contracts-page">Contracts</div>,
  ContractDetailPage: () => <div data-testid="contract-detail">Contract Detail</div>,
  CreateContractPage: () => <div data-testid="create-contract">Create Contract</div>,
}));

vi.mock('./pages/profile/Profile', () => ({
  ProfilePage: () => <div data-testid="profile-page">Profile</div>,
}));

vi.mock('./pages/webhooks/WebhooksPage', () => ({
  WebhooksPage: () => <div data-testid="webhooks-page">Webhooks</div>,
}));

vi.mock('./pages/usage', () => ({
  UsagePage: () => <div data-testid="usage-page">Usage</div>,
}));

vi.mock('./pages/service-accounts/ServiceAccountsPage', () => ({
  ServiceAccountsPage: () => <div data-testid="service-accounts-page">Service Accounts</div>,
}));

vi.mock('./pages/Unauthorized', () => ({
  UnauthorizedPage: () => <div data-testid="unauthorized-page">Unauthorized</div>,
}));

vi.mock('./config', () => ({
  config: {
    api: { baseUrl: 'https://api.gostoa.dev' },
    services: {
      console: { url: 'https://console.gostoa.dev' },
      docs: { url: 'https://docs.gostoa.dev' },
    },
  },
}));

// We test the AppContent (routes) part, not the App wrapper
// because the App wrapper is just ErrorBoundary + AuthProvider + AppContent
import App from './App';

function renderApp(route: string = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.isAuthenticated = true;
    mockAuth.isLoading = false;
    mockAuth.isReady = true;
    mockAuth.user = { id: 'user-1', name: 'Test', roles: ['cpi-admin'] };
    mockAuth.accessToken = 'token';
    mockAuth.hasPermission.mockReturnValue(true);
    mockAuth.hasAnyPermission.mockReturnValue(true);
    mockAuth.hasAllPermissions.mockReturnValue(true);
    mockAuth.hasRole.mockReturnValue(true);
    mockAuth.hasScope.mockReturnValue(true);
  });

  describe('login screen', () => {
    it('should show login screen when not authenticated', () => {
      mockAuth.isAuthenticated = false;

      renderApp('/');

      expect(screen.getByText('Discover AI-powered APIs')).toBeInTheDocument();
      expect(screen.getByText('Request Access')).toBeInTheDocument();
      expect(screen.getByText('Sign In')).toBeInTheDocument();
    });

    it('should show loading screen while authenticating', () => {
      mockAuth.isLoading = true;

      renderApp('/');

      expect(screen.getByRole('img', { name: 'Loading' })).toBeInTheDocument();
    });
  });

  describe('routing', () => {
    it('should render home page on /', async () => {
      renderApp('/');

      expect(await screen.findByTestId('home-page')).toBeInTheDocument();
    });

    it('should render profile page on /profile', async () => {
      renderApp('/profile');

      expect(await screen.findByTestId('profile-page')).toBeInTheDocument();
    });

    it('should render servers page on /servers', async () => {
      renderApp('/servers');

      expect(await screen.findByTestId('servers-page')).toBeInTheDocument();
    });

    it('should render subscriptions page on /subscriptions', async () => {
      renderApp('/subscriptions');

      expect(await screen.findByTestId('subscriptions-page')).toBeInTheDocument();
    });

    it('should render API catalog on /apis', async () => {
      renderApp('/apis');

      expect(await screen.findByTestId('api-catalog')).toBeInTheDocument();
    });

    it('should render apps page on /apps', async () => {
      renderApp('/apps');

      expect(await screen.findByTestId('apps-page')).toBeInTheDocument();
    });

    it('should render contracts page on /contracts', async () => {
      renderApp('/contracts');

      expect(await screen.findByTestId('contracts-page')).toBeInTheDocument();
    });

    it('should render usage page on /usage', async () => {
      renderApp('/usage');

      expect(await screen.findByTestId('usage-page')).toBeInTheDocument();
    });

    it('should redirect unknown routes to home', async () => {
      renderApp('/nonexistent');

      expect(await screen.findByTestId('home-page')).toBeInTheDocument();
    });

    it('should redirect /tools to /servers', async () => {
      renderApp('/tools');

      expect(await screen.findByTestId('servers-page')).toBeInTheDocument();
    });
  });

  describe('RBAC protection', () => {
    it('should redirect to unauthorized when scope check fails', async () => {
      mockAuth.hasScope.mockReturnValue(false);

      renderApp('/servers');

      expect(await screen.findByTestId('unauthorized-page')).toBeInTheDocument();
    });

    it('should redirect to unauthorized when permission check fails', async () => {
      mockAuth.hasPermission.mockReturnValue(false);

      renderApp('/apps');

      expect(await screen.findByTestId('unauthorized-page')).toBeInTheDocument();
    });

    it('should show loading when RBAC checks pending', async () => {
      mockAuth.isReady = false;

      renderApp('/servers');

      expect(screen.getByRole('img', { name: 'Loading' })).toBeInTheDocument();
    });
  });
});
