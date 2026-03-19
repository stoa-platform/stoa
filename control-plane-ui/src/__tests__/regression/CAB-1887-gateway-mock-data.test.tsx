/**
 * Regression test: CAB-1887 — Gateway Dashboard Mock Data
 * PR: #1889, #1890
 * Root cause: GatewayStatus.tsx displayed hardcoded SLO metrics (99.95%, 342ms, 67.2%)
 * and was wired to a single webMethods gateway instead of showing all registered gateways.
 *
 * Invariants protected:
 * 1. No hardcoded SLO/error budget values in the gateway dashboard
 * 2. Overview shows all gateways, not just one (G5)
 * 3. No hardcoded "webMethods Gateway" title
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/usePlatformMetrics', () => ({
  useGatewayHealthSummary: vi.fn(() => ({
    data: { online: 2, offline: 1, degraded: 0, maintenance: 0, total: 3 },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })),
  useGatewayInstances: vi.fn(() => ({
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
        {
          id: 'gw-2',
          display_name: 'Kong Prod',
          gateway_type: 'kong',
          environment: 'production',
          status: 'online',
          base_url: 'https://kong.example.com',
          capabilities: [],
          tags: [],
          auth_config: {},
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
        },
      ],
      total: 2,
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })),
  useGatewayModeStats: vi.fn(() => ({ data: null, isLoading: false, error: null })),
}));

vi.mock('../../hooks/useGatewayStatus', () => ({
  useGatewayPlatformInfo: vi.fn(() => ({
    isLoading: false,
    error: null,
    gatewayComponent: null,
    healthSummary: null,
  })),
}));

vi.mock('../../config', () => ({
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

vi.mock('../../utils/navigation', () => ({
  observabilityPath: (url?: string) => url || '/observability',
  logsPath: () => '/logs',
}));

import GatewayStatus from '../../pages/GatewayStatus';

function renderGatewayStatus() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <GatewayStatus />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('regression/CAB-1887', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('must not display hardcoded SLO value 99.95%', () => {
    renderGatewayStatus();
    expect(screen.queryByText('99.95%')).not.toBeInTheDocument();
  });

  it('must not display hardcoded latency value 342ms', () => {
    renderGatewayStatus();
    expect(screen.queryByText('342ms')).not.toBeInTheDocument();
  });

  it('must not display hardcoded error budget value 67.2%', () => {
    renderGatewayStatus();
    expect(screen.queryByText('67.2%')).not.toBeInTheDocument();
  });

  it('must show multiple gateways, not single webMethods (G5)', () => {
    renderGatewayStatus();
    expect(screen.getByText('STOA Edge')).toBeInTheDocument();
    expect(screen.getByText('Kong Prod')).toBeInTheDocument();
    expect(screen.queryByText('webMethods Gateway')).not.toBeInTheDocument();
  });

  it('must show Gateway Overview title, not single-gateway title (G5)', () => {
    renderGatewayStatus();
    expect(screen.getByText('Gateway Overview')).toBeInTheDocument();
  });
});
