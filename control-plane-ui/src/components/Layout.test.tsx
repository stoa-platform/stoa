import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Layout>{children}</Layout>
    </MemoryRouter>
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

  it('renders gateway-related navigation items', () => {
    renderLayout();
    expect(screen.getByText('Gateway')).toBeInTheDocument();
    expect(screen.getByText('Gateway Registry')).toBeInTheDocument();
    expect(screen.getByText('Gateway Deployments')).toBeInTheDocument();
    expect(screen.getByText('Gateway Metrics')).toBeInTheDocument();
  });

  it('renders breadcrumb component', () => {
    renderLayout();
    expect(screen.getByTestId('breadcrumb')).toBeInTheDocument();
  });

  it('renders STOA title in sidebar', () => {
    renderLayout();
    expect(screen.getByText('STOA')).toBeInTheDocument();
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
