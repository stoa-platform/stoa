import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock api service — only platform status
vi.mock('../../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    get: vi.fn().mockResolvedValue({
      data: {
        gitops: {
          status: 'healthy',
          components: [
            {
              name: 'control-plane-api',
              health_status: 'Healthy',
              sync_status: 'Synced',
              revision: 'abc123',
              last_sync: '2024-01-15T10:00:00Z',
              message: null,
            },
            {
              name: 'stoa-gateway',
              health_status: 'Healthy',
              sync_status: 'Synced',
              revision: 'def456',
              last_sync: '2024-01-15T10:00:00Z',
              message: null,
            },
          ],
          checked_at: '2024-01-15T10:00:00Z',
        },
        events: [
          {
            id: 1,
            component: 'stoa-gateway',
            revision: 'a3f2e1c',
            status: 'Synced',
            timestamp: '2024-01-15T10:00:00Z',
          },
        ],
        external_links: { grafana: '/grafana/' },
        timestamp: '2024-01-15T10:00:00Z',
      },
    }),
  },
}));

// Mock config with dashboards (panels config no longer needed — native components)
vi.mock('../../config', () => ({
  config: {
    services: {
      grafana: {
        url: '/grafana/',
        dashboards: {
          slo: '/grafana/d/stoa-slo-dashboard/slo-dashboard',
          incidentResponse: '/grafana/d/stoa-incident-response/incident-response',
          gatewayFleet: '/grafana/d/stoa-gw-unified/gateway-fleet-unified',
          platformHealth: '/grafana/d/platform-health-l2/platform-health',
          serviceHealth: '/grafana/d/stoa-service-health/service-health',
          gatewayArena: '/grafana/d/gateway-arena/gateway-arena-leaderboard',
        },
      },
      logs: { url: '/logs/' },
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

// Mock MetricCard and MetricTimeseries — render as simple divs
vi.mock('../../components/metrics/MetricCard', () => ({
  MetricCard: ({ label, query }: { label: string; query: string }) => (
    <div data-testid="metric-card" data-query={query}>
      {label}
    </div>
  ),
}));

vi.mock('../../components/metrics/MetricTimeseries', () => ({
  MetricTimeseries: ({ label, query }: { label: string; query: string }) => (
    <div data-testid="metric-timeseries" data-query={query}>
      {label}
    </div>
  ),
}));

import { OperationsDashboard } from './OperationsDashboard';

function renderComponent(role: PersonaRole = 'cpi-admin') {
  vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
  return renderWithProviders(<OperationsDashboard />, { route: '/operations' });
}

describe('OperationsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(
      await screen.findByRole('heading', { name: 'Operations Dashboard' })
    ).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(
      await screen.findByText('Platform health, SLO metrics, and deployment overview')
    ).toBeInTheDocument();
  });

  it('shows Refresh button', () => {
    renderComponent();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('renders SLO Overview section with 4 native metric cards', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('SLO Overview')).toBeInTheDocument();
    });
    expect(screen.getByText('Availability')).toBeInTheDocument();
    expect(screen.getByText('Error Rate')).toBeInTheDocument();
    expect(screen.getByText('P95 Latency')).toBeInTheDocument();
    expect(screen.getByText('Error Budget')).toBeInTheDocument();
  });

  it('renders native metric cards instead of Grafana iframes', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('SLO Overview')).toBeInTheDocument();
    });
    const metricCards = screen.getAllByTestId('metric-card');
    expect(metricCards.length).toBeGreaterThanOrEqual(4);
    // No Grafana iframes
    expect(screen.queryByTestId('grafana-panel')).not.toBeInTheDocument();
  });

  it('renders Platform Health section with ArgoCD components', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Platform Health')).toBeInTheDocument();
    });
    expect(screen.getByText('control-plane-api')).toBeInTheDocument();
    expect(screen.getAllByText('stoa-gateway').length).toBeGreaterThanOrEqual(1);
  });

  it('renders CUJ Health as native metric card', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('CUJ Health Score')).toBeInTheDocument();
    });
  });

  it('shows Recent Deployments section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Recent Deployments')).toBeInTheDocument();
    });
  });

  it('renders Observability Dashboards quick links', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Observability Dashboards')).toBeInTheDocument();
    });
    expect(screen.getByText('SLO Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Incident Response')).toBeInTheDocument();
    expect(screen.getByText('Gateway Fleet')).toBeInTheDocument();
    expect(screen.getByText('Arena Benchmark')).toBeInTheDocument();
    expect(screen.getByText('Service Health')).toBeInTheDocument();
    expect(screen.getByText('Logs Explorer')).toBeInTheDocument();
  });

  it('does NOT render a raw Prometheus link', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Observability Dashboards')).toBeInTheDocument();
    });
    expect(screen.queryByText('Prometheus')).not.toBeInTheDocument();
  });

  // RBAC — Persona-based visibility tests
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page with SLO Overview and Quick Links', async () => {
        renderComponent(role);
        expect(
          await screen.findByRole('heading', { name: 'Operations Dashboard' })
        ).toBeInTheDocument();
        await waitFor(() => {
          expect(screen.getByText('SLO Overview')).toBeInTheDocument();
        });
        expect(screen.getByText('Observability Dashboards')).toBeInTheDocument();
      });
    }
  );

  describe('Traffic & Security RBAC', () => {
    it('shows Traffic & Security for cpi-admin', async () => {
      renderComponent('cpi-admin');
      await waitFor(() => {
        expect(screen.getByText('Traffic & Security')).toBeInTheDocument();
      });
      expect(screen.getByText('Error Rate over Time')).toBeInTheDocument();
      expect(screen.getByText('Active Connections')).toBeInTheDocument();
      expect(screen.getByText('Security Events')).toBeInTheDocument();
      expect(screen.getByText('Fleet RPS')).toBeInTheDocument();
    });

    it('shows Traffic & Security for devops', async () => {
      renderComponent('devops');
      await waitFor(() => {
        expect(screen.getByText('Traffic & Security')).toBeInTheDocument();
      });
    });

    it('hides Traffic & Security for tenant-admin', async () => {
      renderComponent('tenant-admin');
      await waitFor(() => {
        expect(screen.getByText('SLO Overview')).toBeInTheDocument();
      });
      expect(screen.queryByText('Traffic & Security')).not.toBeInTheDocument();
    });

    it('hides Traffic & Security for viewer', async () => {
      renderComponent('viewer');
      await waitFor(() => {
        expect(screen.getByText('SLO Overview')).toBeInTheDocument();
      });
      expect(screen.queryByText('Traffic & Security')).not.toBeInTheDocument();
    });
  });
});
