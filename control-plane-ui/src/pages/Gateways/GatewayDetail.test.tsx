import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { GatewayDetail } from './GatewayDetail';
import type { PersonaRole } from '../../test/helpers';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const { mockGateway, mockDeployments, mockTools } = vi.hoisted(() => ({
  mockGateway: {
    id: 'gw-1',
    name: 'stoa-gateway-edge-mcp-dev',
    display_name: 'STOA Edge MCP Gateway',
    gateway_type: 'stoa_edge_mcp',
    environment: 'dev',
    base_url: 'http://stoa-gateway:8080',
    public_url: 'https://mcp.gostoa.dev',
    target_gateway_url: null,
    auth_config: {},
    status: 'online',
    last_health_check: new Date().toISOString(),
    health_details: {
      uptime_seconds: 7200,
      routes_count: 5,
      policies_count: 2,
      discovered_apis_count: 3,
      discovered_apis: [
        {
          name: 'Weather Service',
          version: '2.0.0',
          backend_url: 'https://api.weather.example.com',
          paths: ['/forecast', '/current'],
          methods: ['GET'],
          policies: [],
          is_active: true,
        },
        {
          name: 'Payment Gateway',
          version: '1.3.0',
          backend_url: 'https://pay.example.com',
          paths: ['/charge', '/refund'],
          methods: ['POST', 'GET'],
          policies: ['rate-limit'],
          is_active: true,
        },
        {
          name: 'Legacy CRM',
          version: '',
          backend_url: 'https://crm.internal',
          paths: ['/contacts'],
          methods: ['GET', 'PUT', 'DELETE'],
          policies: [],
          is_active: false,
        },
      ],
      error_rate: 0.01,
    },
    capabilities: ['rest', 'mcp', 'sse'],
    version: '0.9.1',
    tags: ['auto-registered'],
    mode: 'edge-mcp',
    source: 'self_register',
    protected: false,
    deleted_at: null,
    deleted_by: null,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-02T00:00:00Z',
  },
  mockDeployments: {
    items: [
      {
        id: 'dep-1',
        api_name: 'Payments API',
        api_version: '1.0.0',
        sync_status: 'synced',
        environment: 'dev',
        api_catalog_id: 'payments',
      },
      {
        id: 'dep-2',
        api_name: 'Users API',
        api_version: '2.1.0',
        sync_status: 'pending',
        environment: 'dev',
        api_catalog_id: 'users',
      },
    ],
    total: 2,
  },
  mockTools: [
    { name: 'weather_forecast', description: 'Get weather forecast for a location' },
    { name: 'payment_charge', description: 'Process a payment charge' },
    { name: 'crm_contacts', description: 'List CRM contacts' },
  ],
}));

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayInstance: vi.fn().mockResolvedValue(mockGateway),
    getGatewayDeployments: vi.fn().mockResolvedValue(mockDeployments),
    getGatewayTools: vi.fn().mockResolvedValue(mockTools),
  },
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="skeleton">Loading...</div>,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderGatewayDetail(id = 'gw-1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/gateways/${id}`]}>
        <Routes>
          <Route path="/gateways/:id" element={<GatewayDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GatewayDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders gateway display name', async () => {
    renderGatewayDetail();
    expect(await screen.findByText('STOA Edge MCP Gateway')).toBeInTheDocument();
  });

  it('renders gateway machine name', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('stoa-gateway-edge-mcp-dev')).toBeInTheDocument();
  });

  it('renders status badge', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('online')).toBeInTheDocument();
  });

  it('renders mode badge', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('Edge MCP')).toBeInTheDocument();
  });

  it('renders public_url as clickable link', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    const link = screen.getByText('https://mcp.gostoa.dev');
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toHaveAttribute('href', 'https://mcp.gostoa.dev');
  });

  it('renders Open Gateway button with public_url', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    const openBtn = screen.getByText('Open Gateway');
    expect(openBtn.closest('a')).toHaveAttribute('href', 'https://mcp.gostoa.dev');
  });

  it('renders health metrics', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('2h 0m')).toBeInTheDocument(); // 7200s
    expect(screen.getByText('5')).toBeInTheDocument(); // routes
    expect(screen.getByText('3')).toBeInTheDocument(); // discovered APIs
    expect(screen.getByText('1.0%')).toBeInTheDocument(); // error rate
  });

  it('renders deployed APIs table', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('Payments API')).toBeInTheDocument();
    expect(screen.getByText('Users API')).toBeInTheDocument();
    expect(screen.getByText('2 APIs')).toBeInTheDocument();
  });

  it('renders sync status badges', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('synced')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
  });

  it('renders capabilities', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('rest')).toBeInTheDocument();
    expect(screen.getByText('mcp')).toBeInTheDocument();
    expect(screen.getByText('sse')).toBeInTheDocument();
  });

  it('renders configuration fields', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('http://stoa-gateway:8080')).toBeInTheDocument();
    expect(screen.getAllByText('dev').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('0.9.1')).toBeInTheDocument();
  });

  it('renders MCP tools table when tools are available', async () => {
    const { apiService } = await import('../../services/api');
    vi.mocked(apiService.getGatewayDeployments).mockResolvedValueOnce({
      items: [],
      total: 0,
    });
    renderGatewayDetail();
    expect(await screen.findByText('weather_forecast')).toBeInTheDocument();
    expect(screen.getByText('payment_charge')).toBeInTheDocument();
    expect(screen.getByText('crm_contacts')).toBeInTheDocument();
    expect(screen.getByText('Get weather forecast for a location')).toBeInTheDocument();
    expect(screen.getByText('MCP Tools')).toBeInTheDocument();
  });

  it('renders empty state when no deployments and no tools', async () => {
    const { apiService } = await import('../../services/api');
    vi.mocked(apiService.getGatewayTools).mockResolvedValueOnce([]);
    vi.mocked(apiService.getGatewayDeployments).mockResolvedValueOnce({
      items: [],
      total: 0,
    });
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(
      screen.getByText('No APIs deployed and no MCP tools registered on this gateway')
    ).toBeInTheDocument();
  });

  it('shows both deployed and tools sections when both have data', async () => {
    renderGatewayDetail();
    expect(await screen.findByText('weather_forecast')).toBeInTheDocument();
    expect(screen.getByText('Payments API')).toBeInTheDocument();
    expect(screen.getByText('APIs Deployed')).toBeInTheDocument();
    expect(screen.getByText('MCP Tools')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderGatewayDetail();
        expect(await screen.findByText('STOA Edge MCP Gateway')).toBeInTheDocument();
      });
    }
  );
});
