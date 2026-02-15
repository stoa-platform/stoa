import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// Mock AuthContext
vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

// Mock useGatewayStatus hooks
const mockRefetch = vi.fn();
vi.mock('../hooks/useGatewayStatus', () => ({
  useGatewayStatus: vi.fn(() => ({
    data: {
      health: { status: 'healthy', proxy_mode: false },
      apis: [
        { id: 'api-1', apiName: 'Payment API', apiVersion: '1.0.0', isActive: true },
        { id: 'api-2', apiName: 'User API', apiVersion: '2.0.0', isActive: false },
      ],
      applications: [{ id: 'app-1', name: 'Mobile App' }],
    },
    isLoading: false,
    error: null,
    refetch: mockRefetch,
    dataUpdatedAt: Date.now(),
  })),
  useGatewayPlatformInfo: vi.fn(() => ({
    isLoading: false,
    error: null,
    gatewayComponent: {
      name: 'stoa-gateway',
      sync_status: 'Synced',
      health_status: 'Healthy',
      revision: 'abc1234567890',
      last_sync: '2024-01-15T10:00:00Z',
    },
    healthSummary: {
      healthy: 4,
      progressing: 0,
      degraded: 1,
      total: 5,
    },
  })),
}));

// Mock config
vi.mock('../config', () => ({
  config: {
    services: {
      argocd: {
        url: 'https://argocd.gostoa.dev',
        getAppUrl: (name: string) => `https://argocd.gostoa.dev/applications/${name}`,
      },
      prometheus: { url: 'https://prometheus.gostoa.dev' },
      grafana: { url: '/grafana/' },
    },
  },
}));

// Mock navigation utils
vi.mock('../utils/navigation', () => ({
  observabilityPath: (url?: string) => url || '/observability',
  logsPath: () => '/logs',
}));

import GatewayStatus from './GatewayStatus';

function renderComponent() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <GatewayStatus />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('GatewayStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', () => {
    renderComponent();
    expect(screen.getByRole('heading', { name: 'Gateway Adapters' })).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderComponent();
    expect(screen.getByText(/Zero-Touch GitOps monitoring/)).toBeInTheDocument();
  });

  it('shows webMethods Gateway title', () => {
    renderComponent();
    expect(screen.getByText('webMethods Gateway')).toBeInTheDocument();
  });

  it('shows Connected status badge', () => {
    renderComponent();
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('shows stats cards with API and application counts', () => {
    renderComponent();
    expect(screen.getByText('APIs Synced')).toBeInTheDocument();
    expect(screen.getByText('Applications')).toBeInTheDocument();
    expect(screen.getByText('Last Sync')).toBeInTheDocument();
  });

  it('shows SLO Compliance section', () => {
    renderComponent();
    expect(screen.getByText('SLO Compliance')).toBeInTheDocument();
    expect(screen.getByText('On Track')).toBeInTheDocument();
  });

  it('shows Error Budget section', () => {
    renderComponent();
    expect(screen.getByText('Error Budget')).toBeInTheDocument();
    expect(screen.getByText('67.2%')).toBeInTheDocument();
  });

  it('shows ArgoCD Sync card with status', () => {
    renderComponent();
    expect(screen.getByText('ArgoCD Sync')).toBeInTheDocument();
    expect(screen.getByText('Synced')).toBeInTheDocument();
    // 'Healthy' appears in multiple cards — verify at least one exists
    expect(screen.getAllByText('Healthy').length).toBeGreaterThanOrEqual(1);
  });

  it('shows Observability card', () => {
    renderComponent();
    expect(screen.getByText('Observability')).toBeInTheDocument();
    expect(screen.getByText('Grafana Dashboards')).toBeInTheDocument();
    expect(screen.getByText('Prometheus')).toBeInTheDocument();
    expect(screen.getByText('Logs Explorer')).toBeInTheDocument();
  });

  it('shows Platform Health card with summary', () => {
    renderComponent();
    expect(screen.getByText('Platform Health')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument(); // healthy
    expect(screen.getByText('5 components monitored')).toBeInTheDocument();
  });

  it('shows Zero-Touch GitOps info banner', () => {
    renderComponent();
    expect(screen.getByText('Zero-Touch GitOps')).toBeInTheDocument();
  });

  it('shows Refresh button', () => {
    renderComponent();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('shows loading state when data is loading', async () => {
    const { useGatewayStatus } = await import('../hooks/useGatewayStatus');
    vi.mocked(useGatewayStatus).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: mockRefetch,
      dataUpdatedAt: 0,
    } as any);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <GatewayStatus />
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows error state', async () => {
    const { useGatewayStatus } = await import('../hooks/useGatewayStatus');
    vi.mocked(useGatewayStatus).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Network error'),
      refetch: mockRefetch,
      dataUpdatedAt: 0,
    } as any);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <GatewayStatus />
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText('Failed to load gateway status')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        // Re-import and restore hook mocks (previous tests may have overridden them)
        const hooks = await import('../hooks/useGatewayStatus');
        vi.mocked(hooks.useGatewayStatus).mockReturnValue({
          data: {
            health: { status: 'healthy', proxy_mode: false },
            apis: [{ id: 'api-1', apiName: 'Payment API', apiVersion: '1.0.0', isActive: true }],
            applications: [{ id: 'app-1', name: 'Mobile App' }],
          },
          isLoading: false,
          error: null,
          refetch: mockRefetch,
          dataUpdatedAt: Date.now(),
        } as any);
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(screen.getByText('Gateway Adapters')).toBeInTheDocument();
      });
    }
  );
});
