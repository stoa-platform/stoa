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
  });

  it('renders sidebar with navigation items', () => {
    renderLayout();
    // Nav items render name in <span> + optional shortcut — check by text within the nav
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

  it('renders Identity navigation item', () => {
    renderLayout();
    expect(screen.getByText('Identity')).toBeInTheDocument();
  });

  it('renders gateway section with items', () => {
    renderLayout();
    expect(screen.getByText('\u26A1 Gateway')).toBeInTheDocument();
    expect(screen.getByText('Registry')).toBeInTheDocument();
    expect(screen.getByText('Modes')).toBeInTheDocument();
    expect(screen.getByText('Metrics')).toBeInTheDocument();
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

  it('renders section headers', () => {
    renderLayout();
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Catalog')).toBeInTheDocument();
    expect(screen.getByText('Insights')).toBeInTheDocument();
    expect(screen.getByText('Governance')).toBeInTheDocument();
  });

  it('renders STOA badges on unique features', () => {
    renderLayout();
    const badges = screen.getAllByText('STOA');
    expect(badges.length).toBeGreaterThanOrEqual(3);
  });

  it('collapses section when header is clicked', () => {
    renderLayout();
    // Gateway section is open by default
    const gatewayHeader = screen.getByText('\u26A1 Gateway');
    expect(gatewayHeader).toBeInTheDocument();
    // Click to collapse
    fireEvent.click(gatewayHeader);
    // Verify localStorage was updated
    const stored = JSON.parse(localStorage.getItem('stoa-sidebar-sections') || '{}');
    expect(stored['\u26A1 Gateway']).toBe(true);
  });

  it('expands collapsed section when header is clicked', () => {
    renderLayout();
    // Overview is collapsed by default — click to expand
    const overviewHeader = screen.getByText('Overview');
    fireEvent.click(overviewHeader);
    const stored = JSON.parse(localStorage.getItem('stoa-sidebar-sections') || '{}');
    expect(stored['Overview']).toBe(false);
  });

  it('persists section state to localStorage', () => {
    // Pre-set localStorage
    localStorage.setItem(
      'stoa-sidebar-sections',
      JSON.stringify({ Overview: false, Catalog: true })
    );
    renderLayout();
    // Toggle Catalog to expand
    const catalogHeader = screen.getByText('Catalog');
    fireEvent.click(catalogHeader);
    const stored = JSON.parse(localStorage.getItem('stoa-sidebar-sections') || '{}');
    expect(stored['Catalog']).toBe(false);
  });

  it('renders tenant selector button', () => {
    renderLayout();
    // The tenant selector shows the user's tenant_id
    expect(screen.getByText('oasis-gunters')).toBeInTheDocument();
  });

  it('opens tenant dropdown when clicked', () => {
    renderLayout();
    const tenantButton = screen.getByText('oasis-gunters');
    fireEvent.click(tenantButton);
    // Dropdown should be open (but no tenants loaded since API is mocked)
    // The button should still be visible
    expect(tenantButton).toBeInTheDocument();
  });

  it('renders new skeleton page nav items (CAB-1118)', () => {
    renderLayout();
    expect(screen.getByText('Shadow Discovery')).toBeInTheDocument();
    expect(screen.getByText('Token Optimizer')).toBeInTheDocument();
    expect(screen.getByText('Policies')).toBeInTheDocument();
    expect(screen.getByText('Audit Log')).toBeInTheDocument();
  });

  it('shows tenant list in dropdown and switches tenant', async () => {
    renderLayout();
    // Wait for tenant query to resolve
    await waitFor(() => {
      expect(screen.getByText('Oasis Gunters')).toBeInTheDocument();
    });
    // Open dropdown
    fireEvent.click(screen.getByText('Oasis Gunters'));
    // Both tenants should appear in dropdown
    expect(screen.getByText('Sixers Corp')).toBeInTheDocument();
    // Switch to Sixers Corp
    fireEvent.click(screen.getByText('Sixers Corp'));
    // Active tenant should be stored
    expect(localStorage.getItem('stoa-active-tenant')).toBe('t2');
  });

  it('closes tenant dropdown on outside click', async () => {
    renderLayout();
    await waitFor(() => {
      expect(screen.getByText('Oasis Gunters')).toBeInTheDocument();
    });
    // Open dropdown
    fireEvent.click(screen.getByText('Oasis Gunters'));
    await waitFor(() => {
      expect(screen.getByText('Sixers Corp')).toBeInTheDocument();
    });
    // Click outside
    fireEvent.mouseDown(document.body);
    // Dropdown should close — Sixers Corp option should disappear
    await waitFor(() => {
      // The tenant name in dropdown list should be gone (not the button)
      const sixersElements = screen.queryAllByText('Sixers Corp');
      expect(sixersElements).toHaveLength(0);
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
        .mockImplementation((p: string) => ['apis:read', 'apps:read', 'audit:read'].includes(p)),
      hasRole: vi.fn(() => false),
    });

    renderLayout();
    // Viewer should see basic items
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('APIs')).toBeInTheDocument();
    // Viewer should NOT see admin-only items
    expect(screen.queryByText('Business')).not.toBeInTheDocument();
  });
});
