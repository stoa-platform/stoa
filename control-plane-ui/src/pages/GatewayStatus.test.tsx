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

// Mock usePlatformMetrics hooks (G5: multi-gateway data source)
const mockRefetch = vi.fn();
vi.mock('../hooks/usePlatformMetrics', () => ({
  useGatewayHealthSummary: vi.fn(() => ({
    data: { online: 10, offline: 3, degraded: 2, maintenance: 0, total: 15 },
    isLoading: false,
    error: null,
    refetch: mockRefetch,
  })),
  useGatewayInstances: vi.fn(() => ({
    data: {
      items: [
        {
          id: 'gw-1',
          name: 'stoa-edge',
          display_name: 'STOA Edge MCP',
          gateway_type: 'stoa_edge_mcp',
          environment: 'production',
          base_url: 'https://mcp.gostoa.dev',
          status: 'online',
          last_health_check: new Date().toISOString(),
          capabilities: [],
          tags: [],
          auth_config: {},
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
        },
        {
          id: 'gw-2',
          name: 'kong-prod',
          display_name: 'Kong Production',
          gateway_type: 'kong',
          environment: 'production',
          base_url: 'https://kong.example.com',
          status: 'online',
          last_health_check: new Date().toISOString(),
          capabilities: [],
          tags: [],
          auth_config: {},
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
        },
        {
          id: 'gw-3',
          name: 'wm-staging',
          display_name: 'webMethods Staging',
          gateway_type: 'webmethods',
          environment: 'staging',
          base_url: 'https://wm.example.com',
          status: 'offline',
          capabilities: [],
          tags: [],
          auth_config: {},
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
        },
      ],
      total: 3,
    },
    isLoading: false,
    error: null,
    refetch: mockRefetch,
  })),
  useGatewayModeStats: vi.fn(() => ({
    data: null,
    isLoading: false,
    error: null,
  })),
}));

// Mock useGatewayPlatformInfo (ArgoCD / platform health)
vi.mock('../hooks/useGatewayStatus', () => ({
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
      grafana: { url: '/grafana/', arenaDashboardUrl: '/grafana/d/arena' },
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

  it('renders Gateway Overview heading (G5: not single-gateway title)', () => {
    renderComponent();
    expect(screen.getByRole('heading', { name: 'Gateway Overview' })).toBeInTheDocument();
  });

  it('shows aggregated gateway count in subtitle (G5)', () => {
    renderComponent();
    expect(screen.getByText(/3 gateways/)).toBeInTheDocument();
    expect(screen.getByText(/2 online/)).toBeInTheDocument();
  });

  it('shows stats cards with total, online, STOA, third-party counts (G5)', () => {
    renderComponent();
    expect(screen.getByText('Total Gateways')).toBeInTheDocument();
    // "Online" appears as stats card title AND as gateway row badges
    expect(screen.getAllByText('Online').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('STOA Gateways')).toBeInTheDocument();
    expect(screen.getByText('Third-Party')).toBeInTheDocument();
  });

  it('lists all gateway instances (G5: not just one webMethods)', () => {
    renderComponent();
    expect(screen.getByText('STOA Edge MCP')).toBeInTheDocument();
    expect(screen.getByText('Kong Production')).toBeInTheDocument();
    expect(screen.getByText('webMethods Staging')).toBeInTheDocument();
  });

  it('does NOT show hardcoded webMethods Gateway title (G5)', () => {
    renderComponent();
    expect(screen.queryByText('webMethods Gateway')).not.toBeInTheDocument();
  });

  it('shows SLO and Error Budget without hardcoded values (G3)', () => {
    renderComponent();
    expect(screen.getByText('SLO Compliance')).toBeInTheDocument();
    expect(screen.getByText('Error Budget')).toBeInTheDocument();
    expect(screen.getAllByText('No metrics available')).toHaveLength(2);
    expect(screen.queryByText('99.95%')).not.toBeInTheDocument();
    expect(screen.queryByText('67.2%')).not.toBeInTheDocument();
  });

  it('shows Infrastructure Sync card (G4)', () => {
    renderComponent();
    expect(screen.getByText('Infrastructure Sync')).toBeInTheDocument();
    expect(screen.getByText('Synced')).toBeInTheDocument();
  });

  it('shows Observability card', () => {
    renderComponent();
    expect(screen.getByText('Observability')).toBeInTheDocument();
    expect(screen.getByText('Grafana Dashboards')).toBeInTheDocument();
  });

  it('shows Platform Health card', () => {
    renderComponent();
    expect(screen.getByText('Platform Health')).toBeInTheDocument();
  });

  it('shows Refresh button', () => {
    renderComponent();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('shows loading state', async () => {
    const metrics = await import('../hooks/usePlatformMetrics');
    vi.mocked(metrics.useGatewayHealthSummary).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: mockRefetch,
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
    const metrics = await import('../hooks/usePlatformMetrics');
    vi.mocked(metrics.useGatewayHealthSummary).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Network error'),
      refetch: mockRefetch,
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
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        // Re-import and restore hook mocks (previous tests may have overridden them)
        const metrics = await import('../hooks/usePlatformMetrics');
        vi.mocked(metrics.useGatewayHealthSummary).mockReturnValue({
          data: { online: 2, offline: 1, degraded: 0, maintenance: 0, total: 3 },
          isLoading: false,
          error: null,
          refetch: mockRefetch,
        } as any);
        vi.mocked(metrics.useGatewayInstances).mockReturnValue({
          data: {
            items: [
              {
                id: 'gw-1',
                display_name: 'STOA Edge',
                gateway_type: 'stoa_edge_mcp',
                environment: 'production',
                status: 'online',
                base_url: 'https://mcp.example.com',
                capabilities: [],
                tags: [],
                auth_config: {},
                created_at: '2024-01-01',
                updated_at: '2024-01-01',
              },
            ],
            total: 1,
          },
          isLoading: false,
          error: null,
          refetch: mockRefetch,
        } as any);
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(screen.getByText('Gateway Overview')).toBeInTheDocument();
      });
    }
  );
});
