/**
 * Regression test: CAB-1887 — Gateway Dashboard Mock Data
 * PR: #1889
 * Root cause: GatewayStatus.tsx displayed hardcoded SLO metrics (99.95%, 342ms, 67.2%)
 * and showed "Connected/Disconnected" instead of the unified "Online/Offline" status enum.
 * Failed API calls silently returned 0 instead of showing an error state.
 *
 * Invariants protected:
 * 1. No hardcoded SLO/error budget values in the gateway dashboard
 * 2. Status labels match the Registry page enum (Online/Offline)
 * 3. Failed API fetches show error state, not silent zeros
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

vi.mock('../../hooks/useGatewayStatus', () => ({
  useGatewayStatus: vi.fn(() => ({
    data: {
      health: { status: 'healthy', proxy_mode: false },
      apis: [],
      applications: [],
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    dataUpdatedAt: Date.now(),
  })),
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

  it('must use Online/Offline labels, not Connected/Disconnected', () => {
    renderGatewayStatus();
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(screen.queryByText('Connected')).not.toBeInTheDocument();
    expect(screen.queryByText('Disconnected')).not.toBeInTheDocument();
  });

  it('must show error state when API fetch returns null', async () => {
    const hooks = await import('../../hooks/useGatewayStatus');
    vi.mocked(hooks.useGatewayStatus).mockReturnValue({
      data: {
        health: { status: 'healthy', proxy_mode: false },
        apis: null,
        applications: null,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      dataUpdatedAt: Date.now(),
    } as any);
    renderGatewayStatus();
    expect(screen.getByText(/Unable to fetch/)).toBeInTheDocument();
  });
});
