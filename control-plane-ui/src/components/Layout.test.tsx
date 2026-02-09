import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './Layout';

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
        <Layout>{children}</Layout>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Layout', () => {
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
