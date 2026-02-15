import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock api service
vi.mock('../../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    getBusinessMetrics: vi.fn().mockResolvedValue({
      active_tenants: 12,
      new_tenants_30d: 3,
      tenant_growth: 33.3,
      apdex_score: 0.92,
      total_tokens: 15000,
      total_calls: 5600,
    }),
    getGatewayModeStats: vi.fn().mockResolvedValue({
      modes: [
        { mode: 'edge-mcp', total: 8 },
        { mode: 'sidecar', total: 2 },
      ],
    }),
    getTopAPIs: vi.fn().mockResolvedValue([
      { tool_name: 'weather-api', display_name: 'Weather API', calls: 12450 },
      { tool_name: 'translate-api', display_name: 'Translate API', calls: 8230 },
    ]),
  },
}));

// Mock config
vi.mock('../../config', () => ({
  config: {
    services: {
      grafana: { url: '/grafana/' },
    },
  },
}));

// Mock navigation
vi.mock('../../utils/navigation', () => ({
  observabilityPath: (url?: string) => url || '/observability',
}));

// Mock shared components
vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: ({ className }: { className?: string }) => (
    <div data-testid="card-skeleton" className={className} />
  ),
}));

import { BusinessDashboard } from './BusinessDashboard';

function renderComponent() {
  return render(
    <MemoryRouter>
      <BusinessDashboard />
    </MemoryRouter>
  );
}

describe('BusinessDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'Business Analytics' })).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(
      await screen.findByText('Platform adoption, usage trends, and business metrics')
    ).toBeInTheDocument();
  });

  it('shows KPI cards after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Active Tenants')).toBeInTheDocument();
    });
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('New Tenants (30d)')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('shows token and call metrics', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Total Tokens (Month)')).toBeInTheDocument();
    });
    expect(screen.getByText('15.0K')).toBeInTheDocument();
    expect(screen.getByText('API Calls (Month)')).toBeInTheDocument();
    expect(screen.getByText('5.6K')).toBeInTheDocument();
  });

  it('shows User Satisfaction section with APDEX', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('User Satisfaction')).toBeInTheDocument();
    });
    expect(screen.getByText('0.92')).toBeInTheDocument();
    expect(screen.getByText('APDEX Score')).toBeInTheDocument();
  });

  it('shows Gateway Mode Adoption section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Gateway Mode Adoption')).toBeInTheDocument();
    });
  });

  it('shows Top APIs section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText(/Top APIs by Usage/)).toBeInTheDocument();
    });
    expect(screen.getByText('Weather API')).toBeInTheDocument();
    expect(screen.getByText('Translate API')).toBeInTheDocument();
  });

  it('shows Growth Insights banner', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Growth Insights')).toBeInTheDocument();
    });
  });

  it('shows Refresh button', () => {
    renderComponent();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('shows Advanced Analytics link', () => {
    renderComponent();
    expect(screen.getByText('Advanced Analytics')).toBeInTheDocument();
  });

  it('denies access to non-admin users', async () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
    renderComponent();
    expect(await screen.findByText(/don't have permission/)).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page or denies access', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        if (role === 'cpi-admin') {
          expect(
            await screen.findByRole('heading', { name: 'Business Analytics' })
          ).toBeInTheDocument();
        } else {
          expect(await screen.findByText(/don't have permission/)).toBeInTheDocument();
        }
      });
    }
  );
});
