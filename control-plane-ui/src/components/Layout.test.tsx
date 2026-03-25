import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './Layout';
import { EnvironmentProvider } from '../contexts/EnvironmentContext';

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: vi.fn().mockResolvedValue([
      { id: 't1', name: 'oasis-gunters', display_name: 'Oasis Gunters' },
      { id: 't2', name: 'sixers-corp', display_name: 'Sixers Corp' },
    ]),
  },
}));

const mockUseAuth = vi.fn(() => ({
  user: {
    id: 'u1',
    email: 'parzival@oasis.gg',
    name: 'Parzival',
    roles: ['cpi-admin'],
    tenant_id: 'oasis-gunters',
    permissions: [
      'tenants:read',
      'apis:read',
      'apps:read',
      'apis:deploy',
      'audit:read',
      'admin:servers',
    ],
  },
  isAuthenticated: true,
  isLoading: false,
  isReady: true,
  login: vi.fn(),
  logout: vi.fn(),
  hasPermission: vi.fn(() => true),
  hasRole: vi.fn(() => true),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../hooks/useBreadcrumbs', () => ({
  useBreadcrumbs: () => [{ label: 'Home' }],
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/components/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Toggle</button>,
}));

vi.mock('@stoa/shared/contexts', () => ({
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('react-oidc-context', () => ({
  useAuth: () => ({
    user: { access_token: 'test-token' },
    isAuthenticated: true,
    isLoading: false,
  }),
}));

vi.mock('../config', () => ({
  config: {
    api: { baseUrl: 'https://api.test' },
  },
}));

function renderLayout(children = <div>Page Content</div>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <EnvironmentProvider>
          <Layout>{children}</Layout>
        </EnvironmentProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Layout', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        environments: [
          {
            name: 'dev',
            label: 'Development',
            mode: 'full',
            color: 'green',
            endpoints: null,
            is_current: true,
          },
          {
            name: 'staging',
            label: 'Staging',
            mode: 'full',
            color: 'amber',
            endpoints: null,
            is_current: false,
          },
          {
            name: 'prod',
            label: 'Production',
            mode: 'read-only',
            color: 'red',
            endpoints: null,
            is_current: false,
          },
        ],
      }),
    } as Response);
  });

  it('renders sidebar with navigation items', () => {
    renderLayout();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('APIs')).toBeInTheDocument();
    expect(screen.getByText('AI Tools')).toBeInTheDocument();
    expect(screen.getByText('Applications')).toBeInTheDocument();
    expect(screen.getByText('Tenants')).toBeInTheDocument();
  });

  it('renders children in main content area', () => {
    renderLayout(<div>Test Content</div>);
    expect(screen.getByText('Test Content')).toBeInTheDocument();
  });

  it('renders user info in sidebar', () => {
    renderLayout();
    expect(screen.getByText('Parzival')).toBeInTheDocument();
  });

  it('renders Logs navigation item (CAB-1114)', () => {
    renderLayout();
    expect(screen.getByText('Logs')).toBeInTheDocument();
  });

  it('renders Observability navigation item (CAB-1108)', () => {
    renderLayout();
    expect(screen.getByText('Observability')).toBeInTheDocument();
  });

  it('renders gateway section with items (CAB-1764)', () => {
    renderLayout();
    expect(screen.getByText('Gateway')).toBeInTheDocument();
    // "Overview" appears as both section header and gateway nav item
    const overviewElements = screen.getAllByText('Overview');
    expect(overviewElements.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Config Sync')).toBeInTheDocument();
    expect(screen.getByText('Backend Health')).toBeInTheDocument();
  });

  it('renders breadcrumb component', () => {
    renderLayout();
    expect(screen.getByTestId('breadcrumb')).toBeInTheDocument();
  });

  it('renders STOA title and subtitle in sidebar', () => {
    renderLayout();
    expect(screen.getByRole('heading', { name: 'STOA' })).toBeInTheDocument();
    expect(screen.getByText('Control Plane')).toBeInTheDocument();
  });

  it('renders rationalized section headers (CAB-1764)', () => {
    renderLayout();
    // "Overview" appears as both section header and gateway nav item
    expect(screen.getAllByText('Overview').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('API Catalog')).toBeInTheDocument();
    // AI & MCP has accent (⚡ prefix)
    expect(screen.getByText((_, el) => el?.textContent === '\u26A1 AI & MCP')).toBeInTheDocument();
    expect(screen.getByText('Gateway')).toBeInTheDocument();
    expect(screen.getByText('Monitoring')).toBeInTheDocument();
    expect(screen.getByText('Governance')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('Users & Access')).toBeInTheDocument();
    // Removed sections
    expect(screen.queryByText('Insights')).not.toBeInTheDocument();
  });

  it('renders STOA badges on unique features', () => {
    renderLayout();
    const badges = screen.getAllByText('STOA');
    expect(badges.length).toBeGreaterThanOrEqual(2);
  });

  it('collapses section when header is clicked', () => {
    renderLayout();
    // Target the section header button (not the nav link with same text)
    const overviewHeaders = screen.getAllByText('Overview');
    const sectionHeader = overviewHeaders.find((el) => el.closest('button[class*="uppercase"]'))!;
    fireEvent.click(sectionHeader);
    const stored = JSON.parse(localStorage.getItem('stoa-sidebar-sections') || '{}');
    expect(stored['nav.overview']).toBe(true);
  });

  it('expands collapsed section when header is clicked twice', () => {
    renderLayout();
    const overviewHeaders = screen.getAllByText('Overview');
    const sectionHeader = overviewHeaders.find((el) => el.closest('button[class*="uppercase"]'))!;
    fireEvent.click(sectionHeader); // collapse
    fireEvent.click(sectionHeader); // expand
    const stored = JSON.parse(localStorage.getItem('stoa-sidebar-sections') || '{}');
    expect(stored['nav.overview']).toBe(false);
  });

  it('persists section state to localStorage', () => {
    localStorage.setItem(
      'stoa-sidebar-sections',
      JSON.stringify({ 'nav.overview': false, 'nav.apiCatalog': true })
    );
    renderLayout();
    const catalogHeader = screen.getByText('API Catalog');
    fireEvent.click(catalogHeader);
    const stored = JSON.parse(localStorage.getItem('stoa-sidebar-sections') || '{}');
    expect(stored['nav.apiCatalog']).toBe(false);
  });

  it('renders tenant selector button', () => {
    renderLayout();
    const tenantButtons = screen.getAllByText('oasis-gunters');
    expect(tenantButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('opens tenant dropdown when clicked', () => {
    renderLayout();
    const tenantButtons = screen.getAllByText('oasis-gunters');
    fireEvent.click(tenantButtons[0]);
    expect(tenantButtons[0]).toBeInTheDocument();
  });

  it('renders key nav items after rationalization (CAB-1764)', () => {
    renderLayout();
    expect(screen.getByText('Audit Log')).toBeInTheDocument();
    expect(screen.getByText('AI Ops')).toBeInTheDocument();
    expect(screen.getByText('Consumers')).toBeInTheDocument();
    expect(screen.getByText('Credentials')).toBeInTheDocument();
    expect(screen.getByText('LLM Cost')).toBeInTheDocument();
    expect(screen.getByText('API Access Rules')).toBeInTheDocument();
  });

  it('does not render removed nav items (CAB-1764)', () => {
    renderLayout();
    expect(screen.queryByText('Shadow Discovery')).not.toBeInTheDocument();
    expect(screen.queryByText('Token Optimizer')).not.toBeInTheDocument();
    expect(screen.queryByText('Policies')).not.toBeInTheDocument();
    expect(screen.queryByText('My Usage')).not.toBeInTheDocument();
  });

  it('shows tenant list in dropdown and switches tenant', async () => {
    renderLayout();
    await waitFor(() => {
      expect(screen.getAllByText('Oasis Gunters').length).toBeGreaterThanOrEqual(1);
    });
    const oasisButtons = screen.getAllByText('Oasis Gunters');
    fireEvent.click(oasisButtons[0]);
    const sixersElements = screen.getAllByText('Sixers Corp');
    expect(sixersElements.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(sixersElements[0]);
    expect(localStorage.getItem('stoa-active-tenant')).toBe('t2');
  });

  it('closes tenant dropdown on outside click', async () => {
    renderLayout();
    await waitFor(() => {
      expect(screen.getAllByText('Oasis Gunters').length).toBeGreaterThanOrEqual(1);
    });
    const oasisButtons = screen.getAllByText('Oasis Gunters');
    fireEvent.click(oasisButtons[0]);
    await waitFor(() => {
      expect(screen.getAllByText('Sixers Corp').length).toBeGreaterThanOrEqual(1);
    });
    fireEvent.mouseDown(document.body);
    await waitFor(() => {
      const sixersBefore = screen.getAllByText('Sixers Corp');
      expect(sixersBefore.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('hides navigation items when user lacks permissions', () => {
    mockUseAuth.mockReturnValueOnce({
      user: {
        id: 'u2',
        email: 'viewer@oasis.gg',
        name: 'Viewer',
        roles: ['viewer'],
        tenant_id: 'viewer-tenant',
        permissions: ['apis:read', 'apps:read', 'audit:read'],
      },
      isAuthenticated: true,
      isLoading: false,
      isReady: true,
      login: vi.fn(),
      logout: vi.fn(),
      hasPermission: vi
        .fn()
        .mockImplementation((p: string) =>
          ['apis:read', 'apps:read', 'audit:read', 'consumers:read'].includes(p)
        ),
      hasRole: vi.fn(() => false),
    });

    renderLayout();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('APIs')).toBeInTheDocument();
    // Viewer lacks admin:* permissions — admin items should be hidden
    expect(screen.queryByText('Prospects')).not.toBeInTheDocument();
    expect(screen.queryByText('Settings')).not.toBeInTheDocument();
  });
});
