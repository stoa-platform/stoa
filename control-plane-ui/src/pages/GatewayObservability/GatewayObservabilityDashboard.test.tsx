import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: {
      id: 'user-admin',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      roles: ['cpi-admin'],
      tenant_id: 'oasis-gunters',
      permissions: ['tenants:read', 'apis:read', 'apps:read', 'audit:read', 'admin:servers'],
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

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayAggregatedMetrics: vi.fn().mockResolvedValue({
      health: { total_gateways: 5, online: 3, offline: 1, degraded: 1, maintenance: 0, health_percentage: 80 },
      sync: { total_deployments: 10, synced: 7, pending: 1, syncing: 1, drifted: 1, error: 0, deleting: 0, sync_percentage: 70 },
      overall_status: 'degraded',
    }),
    getBusinessMetrics: vi.fn().mockResolvedValue({
      active_tenants: 12, new_tenants_30d: 3, tenant_growth: 33.3,
      apdex_score: 0.92, total_tokens: 15000, total_calls: 5600,
    }),
  },
}));

vi.mock('../../config', () => ({
  config: {
    services: {
      grafana: { url: '/grafana/' },
    },
  },
}));

vi.mock('../../utils/navigation', () => ({
  observabilityPath: (url: string) => url,
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/contexts', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: ({ className }: { className?: string }) => <div data-testid="card-skeleton" className={className} />,
}));

import { GatewayObservabilityDashboard } from './GatewayObservabilityDashboard';

function renderDashboard() {
  return render(
    <MemoryRouter>
      <GatewayObservabilityDashboard />
    </MemoryRouter>
  );
}

describe('GatewayObservabilityDashboard', () => {
  it('renders the page heading', async () => {
    renderDashboard();
    expect(await screen.findByText('Gateway Observability')).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderDashboard();
    expect(
      await screen.findByText('Health and sync metrics across all gateway instances')
    ).toBeInTheDocument();
  });

  it('renders the overall status badge (DEGRADED)', async () => {
    renderDashboard();
    expect(await screen.findByText('DEGRADED')).toBeInTheDocument();
  });

  it('renders the Gateway Health section heading', async () => {
    renderDashboard();
    // Wait for data load (DEGRADED only appears after metrics resolve)
    await screen.findByText('DEGRADED');
    // "Gateway Health" appears as both section heading and progress bar label
    const healthElements = screen.getAllByText('Gateway Health');
    expect(healthElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the total gateways stat card', async () => {
    renderDashboard();
    await screen.findByText('DEGRADED');
    // "Total" appears in both health and sync sections
    const totals = screen.getAllByText('Total');
    expect(totals.length).toBe(2);
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('renders online and degraded gateway counts', async () => {
    renderDashboard();
    await screen.findByText('DEGRADED');
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Degraded')).toBeInTheDocument();
  });

  it('renders the Deployment Sync Status section', async () => {
    renderDashboard();
    expect(await screen.findByText('Deployment Sync Status', {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it('renders the APDEX Score gauge', async () => {
    renderDashboard();
    expect(await screen.findByText('APDEX Score', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText('0.92')).toBeInTheDocument();
  });

  it('renders the Open in Grafana button', async () => {
    renderDashboard();
    expect(await screen.findByText('Open in Grafana')).toBeInTheDocument();
  });

  it('renders the Refresh button', async () => {
    renderDashboard();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });
});
