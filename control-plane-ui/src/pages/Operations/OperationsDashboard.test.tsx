import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

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

// Mock api service
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
              name: 'mcp-gateway',
              health_status: 'Healthy',
              sync_status: 'Synced',
              revision: 'def456',
              last_sync: '2024-01-15T10:00:00Z',
              message: null,
            },
          ],
          checked_at: '2024-01-15T10:00:00Z',
        },
        events: [],
        external_links: { grafana: '/grafana/', prometheus: 'https://prometheus.gostoa.dev' },
        timestamp: '2024-01-15T10:00:00Z',
      },
    }),
    getGatewayAggregatedMetrics: vi.fn().mockResolvedValue({
      health: {
        total_gateways: 5,
        online: 3,
        offline: 1,
        degraded: 1,
        maintenance: 0,
        health_percentage: 80,
      },
      sync: {
        total_deployments: 10,
        synced: 7,
        pending: 1,
        syncing: 1,
        drifted: 1,
        error: 0,
        deleting: 0,
        sync_percentage: 70,
      },
      overall_status: 'DEGRADED',
    }),
    getOperationsMetrics: vi.fn().mockResolvedValue({
      error_rate: 0.05,
      p95_latency_ms: 342,
      requests_per_minute: 120,
      active_alerts: 0,
      uptime: 99.95,
    }),
  },
}));

// Mock config
vi.mock('../../config', () => ({
  config: {
    services: {
      grafana: { url: '/grafana/' },
      prometheus: { url: 'https://prometheus.gostoa.dev' },
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

import { OperationsDashboard } from './OperationsDashboard';

function renderComponent() {
  return render(
    <MemoryRouter>
      <OperationsDashboard />
    </MemoryRouter>
  );
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
      await screen.findByText('Platform health, performance metrics, and incident overview')
    ).toBeInTheDocument();
  });

  it('shows key metrics after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Platform Health')).toBeInTheDocument();
    });
    expect(screen.getByText('Error Rate (5m)')).toBeInTheDocument();
    expect(screen.getByText('P95 Latency')).toBeInTheDocument();
    expect(screen.getByText('Active Alerts')).toBeInTheDocument();
    expect(screen.getByText('Requests/min')).toBeInTheDocument();
  });

  it('shows platform health percentage', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('100%')).toBeInTheDocument();
    });
    expect(screen.getByText('2/2 components')).toBeInTheDocument();
  });

  it('shows gateway health section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Gateway Health')).toBeInTheDocument();
    });
    expect(screen.getByText('5')).toBeInTheDocument(); // total gateways
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(screen.getByText('Degraded')).toBeInTheDocument();
    expect(screen.getByText('Offline')).toBeInTheDocument();
  });

  it('shows All Systems Operational when no alerts', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('All Systems Operational')).toBeInTheDocument();
    });
  });

  it('shows observability tools section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Observability Tools')).toBeInTheDocument();
    });
    expect(screen.getByText('Grafana')).toBeInTheDocument();
    expect(screen.getByText('Prometheus')).toBeInTheDocument();
    expect(screen.getByText('API Monitoring')).toBeInTheDocument();
    expect(screen.getByText('Error Snapshots')).toBeInTheDocument();
  });

  it('shows Refresh button', () => {
    renderComponent();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('shows Recent Deployments section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Recent Deployments')).toBeInTheDocument();
    });
  });

  it('shows Active Incidents section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Active Incidents')).toBeInTheDocument();
    });
  });
});
