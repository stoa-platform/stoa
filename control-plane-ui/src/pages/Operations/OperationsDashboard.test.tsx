import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock api service — only platform status (no more gateway metrics or operations metrics)
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

// Mock config with panels + dashboards
vi.mock('../../config', () => ({
  config: {
    services: {
      grafana: {
        url: '/grafana/',
        panels: {
          sloAvailability: { uid: 'stoa-slo-dashboard', panelId: 1 },
          sloLatencyP95: { uid: 'stoa-slo-dashboard', panelId: 2 },
          sloErrorRate: { uid: 'stoa-slo-dashboard', panelId: 3 },
          sloErrorBudget: { uid: 'stoa-slo-dashboard', panelId: 4 },
          errorRateTimeseries: { uid: 'stoa-incident-response', panelId: 0 },
          latencyP99: { uid: 'stoa-incident-response', panelId: 1 },
          activeConnections: { uid: 'stoa-incident-response', panelId: 5 },
          securityEvents: { uid: 'stoa-incident-response', panelId: 6 },
          fleetRps: { uid: 'stoa-gw-unified', panelId: 2 },
          platformCujPassing: { uid: 'platform-health-l2', panelId: 1 },
        },
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

// Mock GrafanaPanel — render as a simple div with title
vi.mock('../../components/GrafanaPanel', () => ({
  GrafanaPanel: ({
    title,
    dashboardUid,
    panelId,
  }: {
    title?: string;
    dashboardUid: string;
    panelId: number;
  }) => (
    <div data-testid="grafana-panel" data-uid={dashboardUid} data-panel-id={panelId}>
      {title}
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

  it('renders SLO Overview section with 4 Grafana panels', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('SLO Overview')).toBeInTheDocument();
    });
    expect(screen.getByText('Availability')).toBeInTheDocument();
    expect(screen.getByText('Error Rate')).toBeInTheDocument();
    expect(screen.getByText('P95 Latency')).toBeInTheDocument();
    expect(screen.getByText('Error Budget')).toBeInTheDocument();
  });

  it('renders Platform Health section with ArgoCD components', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Platform Health')).toBeInTheDocument();
    });
    expect(screen.getByText('control-plane-api')).toBeInTheDocument();
    expect(screen.getAllByText('stoa-gateway').length).toBeGreaterThanOrEqual(1);
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

  it('renders Grafana panel embeds with correct UIDs', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('SLO Overview')).toBeInTheDocument();
    });
    const panels = screen.getAllByTestId('grafana-panel');
    const sloPanel = panels.find((p) => p.getAttribute('data-uid') === 'stoa-slo-dashboard');
    expect(sloPanel).toBeTruthy();
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
