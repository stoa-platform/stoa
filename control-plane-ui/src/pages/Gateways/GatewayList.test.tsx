import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const { mockGateways } = vi.hoisted(() => ({
  mockGateways: [
    {
      id: 'gw-1',
      name: 'stoa-edge-mcp-1',
      display_name: 'STOA Edge MCP Gateway',
      gateway_type: 'stoa_edge_mcp',
      environment: 'dev',
      base_url: 'https://mcp.gostoa.dev',
      auth_config: {},
      status: 'online',
      last_health_check: new Date().toISOString(),
      health_details: {
        uptime_seconds: 3600,
        routes_count: 10,
        policies_count: 3,
        requests_total: 1500,
        error_rate: 0.02,
        registered_at: '2024-01-01T00:00:00Z',
      },
      capabilities: ['mcp', 'openapi', 'rate_limiting'],
      tags: ['production'],
      mode: 'edge-mcp',
      version: '0.1.0',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-15T00:00:00Z',
    },
    {
      id: 'gw-2',
      name: 'webmethods-prod',
      display_name: 'webMethods Production',
      gateway_type: 'webmethods',
      environment: 'prod',
      base_url: 'https://wm.example.com',
      auth_config: {},
      status: 'degraded',
      last_health_check: '2024-01-01T00:00:00Z',
      health_details: { error_rate: 0.08 },
      capabilities: ['rest', 'soap'],
      tags: ['legacy'],
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-10T00:00:00Z',
    },
  ],
}));

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
    getGatewayInstances: vi.fn().mockResolvedValue({
      items: mockGateways,
      total: 2,
    }),
    checkGatewayHealth: vi.fn().mockResolvedValue({ status: 'online' }),
    deleteGatewayInstance: vi.fn().mockResolvedValue(undefined),
    registerGateway: vi.fn().mockResolvedValue({}),
  },
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

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { GatewayList } from './GatewayList';

function renderGatewayList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <GatewayList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('GatewayList', () => {
  it('renders gateway display names', async () => {
    renderGatewayList();
    expect(await screen.findByText('STOA Edge MCP Gateway')).toBeInTheDocument();
    expect(screen.getByText('webMethods Production')).toBeInTheDocument();
  });

  it('renders gateway status badges', async () => {
    renderGatewayList();
    expect(await screen.findByText('online')).toBeInTheDocument();
    expect(screen.getByText('degraded')).toBeInTheDocument();
  });

  it('renders the mode filter dropdown', async () => {
    renderGatewayList();
    // The option text includes count: "All Modes (N)"
    expect(await screen.findByText(/All Modes/)).toBeInTheDocument();
  });

  it('renders gateway environment labels', async () => {
    renderGatewayList();
    expect(await screen.findByText('dev')).toBeInTheDocument();
    expect(screen.getByText('prod')).toBeInTheDocument();
  });

  it('renders the Edge MCP mode badge', async () => {
    renderGatewayList();
    expect(await screen.findByText('Edge MCP')).toBeInTheDocument();
  });

  it('renders the gateway type labels', async () => {
    renderGatewayList();
    expect(await screen.findByText('STOA Edge MCP')).toBeInTheDocument();
    expect(screen.getByText('webMethods')).toBeInTheDocument();
  });

  it('renders gateway base URLs', async () => {
    renderGatewayList();
    expect(await screen.findByText('https://mcp.gostoa.dev')).toBeInTheDocument();
    expect(screen.getByText('https://wm.example.com')).toBeInTheDocument();
  });

  it('renders live indicator (green pulse) for gateway with recent heartbeat', async () => {
    renderGatewayList();
    await screen.findByText('STOA Edge MCP Gateway');
    // gw-1 has recent last_health_check -> should have "Live" title
    const liveIndicators = screen.getAllByTitle('Live (heartbeat active)');
    expect(liveIndicators.length).toBeGreaterThanOrEqual(1);
  });

  it('renders gray indicator for gateway with old heartbeat', async () => {
    renderGatewayList();
    await screen.findByText('webMethods Production');
    // gw-2 has old last_health_check -> should have "No recent heartbeat" title
    const offlineIndicators = screen.getAllByTitle('No recent heartbeat');
    expect(offlineIndicators.length).toBeGreaterThanOrEqual(1);
  });

  it('opens detail panel when clicking a gateway card', async () => {
    renderGatewayList();
    const gatewayCard = await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(gatewayCard);
    // Detail panel should appear with heartbeat metrics section
    expect(screen.getByTestId('gateway-detail-panel')).toBeInTheDocument();
    expect(screen.getByText('Heartbeat Metrics')).toBeInTheDocument();
  });

  it('shows heartbeat metrics in detail panel', async () => {
    renderGatewayList();
    const gatewayCard = await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(gatewayCard);
    // Check metric values from health_details
    expect(screen.getByText('1h 0m')).toBeInTheDocument(); // uptime_seconds: 3600
    expect(screen.getByText('10')).toBeInTheDocument(); // routes_count
    expect(screen.getByText('1500')).toBeInTheDocument(); // requests_total
    expect(screen.getByText('2.0%')).toBeInTheDocument(); // error_rate: 0.02
  });

  it('closes detail panel when clicking close button', async () => {
    renderGatewayList();
    const gatewayCard = await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(gatewayCard);
    expect(screen.getByTestId('gateway-detail-panel')).toBeInTheDocument();
    const closeButton = screen.getByLabelText('Close detail panel');
    fireEvent.click(closeButton);
    expect(screen.queryByTestId('gateway-detail-panel')).not.toBeInTheDocument();
  });

  it('shows degraded badge when error rate > 5%', async () => {
    renderGatewayList();
    const gatewayCard = await screen.findByText('webMethods Production');
    fireEvent.click(gatewayCard);
    // gw-2 has error_rate: 0.08 (> 0.05) -> should show degraded badge
    expect(screen.getByText(/degraded \(error rate/)).toBeInTheDocument();
  });
});
