import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: {
      id: 'user-admin',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      roles: ['cpi-admin'],
      tenant_id: 'oasis-gunters',
      permissions: ['tenants:read', 'apis:read', 'apps:read', 'audit:read', 'admin:servers'],
    },
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    login: vi.fn(),
    logout: vi.fn(),
    hasPermission: vi.fn(() => true),
    hasRole: vi.fn(() => true),
  })),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    getTenants: vi.fn().mockResolvedValue([]),
    getPlatformStatus: vi.fn().mockResolvedValue({
      gitops: { status: 'healthy', components: [], checked_at: '' },
      events: [],
      external_links: {},
      timestamp: '',
    }),
    getPlatformComponents: vi.fn().mockResolvedValue([]),
    getPlatformEvents: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/contexts', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('../hooks/useBreadcrumbs', () => ({
  useBreadcrumbs: () => [{ label: 'Home' }],
}));

vi.mock('@stoa/shared/components/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Toggle</button>,
}));

vi.mock('react-oidc-context', () => ({
  useAuth: () => ({ isAuthenticated: true, isLoading: false, user: null }),
  hasAuthParams: () => false,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('../services/mcpGatewayApi', () => ({
  mcpGatewayService: { setAuthToken: vi.fn(), clearAuthToken: vi.fn() },
}));

import App from '../App';

function renderApp(route = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Dashboard', () => {
  it('renders the Dashboard heading', async () => {
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('renders the welcome subtitle', async () => {
    renderApp('/');
    expect(await screen.findByText('Welcome to STOA Control Plane')).toBeInTheDocument();
  });

  it('greets the authenticated user by name', async () => {
    renderApp('/');
    expect(await screen.findByText('Hello, Parzival!')).toBeInTheDocument();
  });

  it('shows the user email', async () => {
    renderApp('/');
    expect(await screen.findByText('parzival@oasis.gg')).toBeInTheDocument();
  });

  it('renders the four quick action card descriptions', async () => {
    renderApp('/');
    expect(await screen.findByText('Manage API definitions and deployments')).toBeInTheDocument();
    expect(screen.getByText('Browse MCP tools catalog')).toBeInTheDocument();
    expect(screen.getByText('Manage consumer applications')).toBeInTheDocument();
    expect(screen.getByText('View deployment history')).toBeInTheDocument();
  });

  it('renders the Getting Started section', async () => {
    renderApp('/');
    expect(await screen.findByText('Getting Started')).toBeInTheDocument();
  });

  it('renders the Quick Links section', async () => {
    renderApp('/');
    expect(await screen.findByText('Quick Links')).toBeInTheDocument();
  });
});
