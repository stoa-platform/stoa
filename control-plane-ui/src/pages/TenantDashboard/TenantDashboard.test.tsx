import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: {
      id: 'user-admin',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      roles: ['cpi-admin'],
      tenant_id: 'oasis-gunters',
      permissions: ['tenants:read'],
    },
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    login: vi.fn(),
    logout: vi.fn(),
    hasPermission: vi.fn(() => true),
    hasRole: vi.fn(() => true),
  })),
}));

// Mock shared components
vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: ({ className }: { className?: string }) => (
    <div data-testid="card-skeleton" className={className} />
  ),
}));

import { TenantDashboard } from './TenantDashboard';

function renderComponent() {
  return render(<TenantDashboard />);
}

describe('TenantDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'My Usage' })).toBeInTheDocument();
  });

  it('shows tenant ID in subtitle', async () => {
    renderComponent();
    expect(await screen.findByText('oasis-gunters')).toBeInTheDocument();
  });

  it('shows period selector buttons', async () => {
    renderComponent();
    expect(await screen.findByText('7d')).toBeInTheDocument();
    expect(screen.getByText('30d')).toBeInTheDocument();
    expect(screen.getByText('This Month')).toBeInTheDocument();
  });

  it('shows key metric cards after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('API Calls')).toBeInTheDocument();
    });
    expect(screen.getByText('Tokens Consumed')).toBeInTheDocument();
    expect(screen.getByText('SLA Compliance')).toBeInTheDocument();
    expect(screen.getByText('Estimated Cost')).toBeInTheDocument();
  });

  it('shows secondary metrics', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Avg Latency')).toBeInTheDocument();
    });
    expect(screen.getByText('Error Rate')).toBeInTheDocument();
  });

  it('shows Top 5 Tools section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Top 5 Tools')).toBeInTheDocument();
    });
    expect(screen.getByText('Weather API')).toBeInTheDocument();
    expect(screen.getByText('Translate API')).toBeInTheDocument();
  });

  it('shows Usage Trend section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText(/Usage Trend/)).toBeInTheDocument();
    });
  });

  it('shows SLA Summary section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('SLA Summary')).toBeInTheDocument();
    });
    expect(screen.getByText('Availability')).toBeInTheDocument();
    expect(screen.getByText('Latency P95')).toBeInTheDocument();
    expect(screen.getByText('Error Budget')).toBeInTheDocument();
  });

  it('shows Refresh button', async () => {
    renderComponent();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });

  it('shows no tenant message when tenant_id is missing', async () => {
    const { useAuth } = await import('../../contexts/AuthContext');
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 'user-no-tenant',
        email: 'no@tenant.com',
        name: 'NoTenant',
        roles: ['viewer'],
        tenant_id: undefined,
        permissions: [],
      },
      isAuthenticated: true,
      isLoading: false,
      isReady: true,
      login: vi.fn(),
      logout: vi.fn(),
      hasPermission: vi.fn(() => false),
      hasRole: vi.fn(() => false),
    } as any);
    renderComponent();
    expect(await screen.findByText(/Tenant information not available/)).toBeInTheDocument();
  });
});
