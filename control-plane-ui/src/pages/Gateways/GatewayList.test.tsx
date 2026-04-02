import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

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
      environment: 'production',
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
      environment: 'staging',
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
    {
      id: 'gw-3',
      name: 'argocd-kong-dataplane',
      display_name: 'Kong Dataplane',
      gateway_type: 'kong',
      environment: 'production',
      base_url: 'http://kong-dataplane.stoa-dataplane.svc.cluster.local',
      auth_config: {},
      status: 'online',
      last_health_check: new Date().toISOString(),
      health_details: {
        argocd_health: 'Healthy',
        argocd_sync: 'Synced',
        argocd_revision: 'abc12345',
      },
      capabilities: ['rest'],
      tags: ['argocd-managed'],
      source: 'argocd',
      created_at: '2024-03-01T00:00:00Z',
      updated_at: '2024-03-11T00:00:00Z',
    },
  ],
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../contexts/EnvironmentContext', () => ({
  useEnvironment: () => ({
    activeEnvironment: 'dev',
    activeConfig: { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
    environments: [
      { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
      { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
      { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' },
    ],
    switchEnvironment: vi.fn(),
  }),
}));

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayInstances: vi.fn().mockResolvedValue({
      items: mockGateways,
      total: 3,
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
    </QueryClientProvider>
  );
}

describe('GatewayList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders gateway display names', async () => {
    renderGatewayList();
    expect(await screen.findByText('STOA Edge MCP Gateway')).toBeInTheDocument();
    expect(screen.getByText('webMethods Production')).toBeInTheDocument();
  });

  it('renders gateway status badges with capitalized labels', async () => {
    renderGatewayList();
    await screen.findByText('STOA Edge MCP Gateway');
    // New UI uses STATUS_CONFIG with capitalized labels
    expect(screen.getAllByText('Online').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Degraded').length).toBeGreaterThanOrEqual(1);
  });

  it('renders environment tabs', async () => {
    renderGatewayList();
    await screen.findByText('STOA Edge MCP Gateway');
    // Environment tabs replace the mode filter dropdown
    const nav = screen.getByRole('navigation', { name: 'Environment tabs' });
    expect(nav).toBeInTheDocument();
    // "All" tab and environment tabs
    expect(screen.getByText('All')).toBeInTheDocument();
    // Production and Staging appear in both tabs and section headers — getAllByText
    expect(screen.getAllByText('Production').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Staging').length).toBeGreaterThanOrEqual(1);
  });

  it('groups gateways by environment', async () => {
    renderGatewayList();
    await screen.findByText('STOA Edge MCP Gateway');
    // Both env section headers visible (Production for gw-1, Staging for gw-2)
    expect(screen.getAllByText('Production').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Staging').length).toBeGreaterThanOrEqual(1);
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

  it('renders gateway base URLs (protocol stripped)', async () => {
    renderGatewayList();
    await screen.findByText('STOA Edge MCP Gateway');
    // New UI strips protocol from URLs in the row view
    expect(screen.getByText('mcp.gostoa.dev')).toBeInTheDocument();
    expect(screen.getByText('wm.example.com')).toBeInTheDocument();
  });

  it('renders status dot with title for live gateway', async () => {
    renderGatewayList();
    await screen.findByText('STOA Edge MCP Gateway');
    // gw-1 has recent last_health_check -> status dot title includes "live heartbeat"
    const liveDots = screen.getAllByTitle(/live heartbeat/i);
    expect(liveDots.length).toBeGreaterThanOrEqual(1);
  });

  it('renders status dot title for non-live gateway', async () => {
    renderGatewayList();
    await screen.findByText('webMethods Production');
    // gw-2 has old last_health_check -> status dot title is just "Degraded"
    const statusDots = screen.getAllByTitle('Degraded');
    expect(statusDots.length).toBeGreaterThanOrEqual(1);
  });

  it('navigates to detail page when clicking a gateway row (CAB-1940)', async () => {
    renderGatewayList();
    const gatewayName = await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(gatewayName);
    expect(mockNavigate).toHaveBeenCalledWith('/gateways/gw-1');
  });

  it('navigates to correct gateway on different row click (CAB-1940)', async () => {
    renderGatewayList();
    const gatewayName = await screen.findByText('webMethods Production');
    fireEvent.click(gatewayName);
    expect(mockNavigate).toHaveBeenCalledWith('/gateways/gw-2');
  });

  it('renders GitOps badge for argocd-sourced gateways', async () => {
    renderGatewayList();
    await screen.findByText('Kong Dataplane');
    // ArgoCD-sourced gateways show "GitOps" badge
    expect(screen.getAllByText('GitOps').length).toBeGreaterThanOrEqual(1);
  });

  it('navigates to argocd gateway detail page (CAB-1940)', async () => {
    renderGatewayList();
    const gatewayName = await screen.findByText('Kong Dataplane');
    fireEvent.click(gatewayName);
    expect(mockNavigate).toHaveBeenCalledWith('/gateways/gw-3');
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderGatewayList();
        expect(await screen.findByText('STOA Edge MCP Gateway')).toBeInTheDocument();
      });
    }
  );

  // CAB-1673: Structural snapshot guards
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'snapshot: %s persona',
    (role) => {
      it('matches structural snapshot', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        const { container } = renderGatewayList();
        await screen.findByText('STOA Edge MCP Gateway');
        const buttons = [...container.querySelectorAll('button')].map(
          (b) => b.textContent?.trim() || ''
        );
        const headings = [...container.querySelectorAll('h1, h2, h3')].map(
          (h) => h.textContent?.trim() || ''
        );
        const links = [...container.querySelectorAll('a[href]')].map((a) => ({
          text: a.textContent?.trim() || '',
          href: a.getAttribute('href'),
        }));
        expect({ buttons, headings, links }).toMatchSnapshot();
      });
    }
  );
});
