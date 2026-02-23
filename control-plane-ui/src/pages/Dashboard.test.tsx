import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';
// Initialize i18n singleton so useTranslation resolves correctly in tests
import '../i18n/i18n';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
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
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

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
    expect(await screen.findByText('Hello, James Halliday!')).toBeInTheDocument();
  });

  it('shows the user email', async () => {
    renderApp('/');
    expect(await screen.findByText('halliday@gregarious-games.com')).toBeInTheDocument();
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

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderApp('/');
        expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
      });
    }
  );
});
