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

// Mock config with dashboards
vi.mock('../../config', () => ({
  config: {
    services: {
      grafana: {
        url: '/grafana/',
        dashboards: {
          slo: '/grafana/d/stoa-slo-dashboard/slo-dashboard',
          gatewayRed: '/grafana/d/stoa-gateway-red/gateway-red-method',
          controlPlaneApi: '/grafana/d/stoa-control-plane-api/control-plane-api',
          platformOverview: '/grafana/d/stoa-platform-overview/platform-overview',
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

// Mock MetricCard — render as simple divs
vi.mock('../../components/metrics/MetricCard', () => ({
  MetricCard: ({ label, query }: { label: string; query: string }) => (
    <div data-testid="metric-card" data-query={query}>
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
      await screen.findByText('SLO metrics, ArgoCD status, and deployment overview')
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
    expect(screen.queryByTestId('grafana-panel')).not.toBeInTheDocument();
  });

  it('renders ArgoCD Components section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('ArgoCD Components')).toBeInTheDocument();
    });
    expect(screen.getByText('control-plane-api')).toBeInTheDocument();
    expect(screen.getAllByText('stoa-gateway').length).toBeGreaterThanOrEqual(1);
  });

  it('renders Platform Activity with API and MCP metrics', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Platform Activity')).toBeInTheDocument();
    });
    expect(screen.getByText('API Requests/h')).toBeInTheDocument();
    expect(screen.getByText('API In Progress')).toBeInTheDocument();
    expect(screen.getByText('MCP Tool Calls/h')).toBeInTheDocument();
  });

  it('shows "Full metrics" link to /observability', async () => {
    renderComponent();
    expect(await screen.findByText('Full metrics')).toBeInTheDocument();
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
    expect(screen.getByText('Gateway RED Method')).toBeInTheDocument();
    expect(screen.getByText('Control Plane API')).toBeInTheDocument();
    expect(screen.getByText('Platform Overview')).toBeInTheDocument();
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

  it('does NOT render Traffic & Security section (moved to /observability)', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('SLO Overview')).toBeInTheDocument();
    });
    expect(screen.queryByText('Traffic & Security')).not.toBeInTheDocument();
  });

  // RBAC — all personas see the same content (no RBAC-restricted sections remain)
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

  // Regression: PR #1649 — PromQL queries used wrong label name `code` instead of `status`
  // for Gateway metrics and missed `status_code` for Control Plane API metrics.
  // These tests verify the MetricCard queries contain the correct label names.
  describe('regression/operations-promql-queries', () => {
    it('SLO availability query uses status (not code) for Gateway and status_code for API', async () => {
      renderComponent();
      await waitFor(() => {
        expect(screen.getByText('SLO Overview')).toBeInTheDocument();
      });
      const metricCards = screen.getAllByTestId('metric-card');
      const availabilityCard = metricCards.find((el) => el.textContent?.includes('Availability'));
      expect(availabilityCard).toBeDefined();
      const query = availabilityCard!.getAttribute('data-query') || '';
      // Must use `status=~"5.."` for Gateway metric (not `code=~"5.."`)
      expect(query).toContain('stoa_http_requests_total{status=~"5.."}');
      expect(query).not.toContain('{code=~');
      // Must include Control Plane API metric with `status_code` label
      expect(query).toContain('stoa_control_plane_http_requests_total{status_code=~"5.."}');
    });

    it('SLO error rate query uses status (not code) for Gateway and status_code for API', async () => {
      renderComponent();
      await waitFor(() => {
        expect(screen.getByText('SLO Overview')).toBeInTheDocument();
      });
      const metricCards = screen.getAllByTestId('metric-card');
      const errorRateCard = metricCards.find((el) => el.textContent?.includes('Error Rate'));
      expect(errorRateCard).toBeDefined();
      const query = errorRateCard!.getAttribute('data-query') || '';
      expect(query).toContain('stoa_http_requests_total{status=~"5.."}');
      expect(query).not.toContain('{code=~');
      expect(query).toContain('stoa_control_plane_http_requests_total{status_code=~"5.."}');
    });

    it('SLO error budget query uses status (not code) label', async () => {
      renderComponent();
      await waitFor(() => {
        expect(screen.getByText('SLO Overview')).toBeInTheDocument();
      });
      const metricCards = screen.getAllByTestId('metric-card');
      const budgetCard = metricCards.find((el) => el.textContent?.includes('Error Budget'));
      expect(budgetCard).toBeDefined();
      const query = budgetCard!.getAttribute('data-query') || '';
      expect(query).toContain('stoa_http_requests_total{status=~"5.."}');
      expect(query).not.toContain('{code=~');
    });
  });
});
