import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { GatewayDetail } from './GatewayDetail';
import type { PersonaRole } from '../../test/helpers';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const { mockGateway, mockDeployments, mockTools, mockOverview } = vi.hoisted(() => ({
  mockGateway: {
    id: 'gw-1',
    name: 'stoa-gateway-edge-mcp-dev',
    display_name: 'STOA Edge MCP Gateway',
    gateway_type: 'stoa_edge_mcp',
    environment: 'dev',
    base_url: 'http://stoa-gateway:8080',
    public_url: 'https://mcp.gostoa.dev',
    target_gateway_url: null,
    ui_url: null,
    endpoints: null,
    deployment_mode: null,
    target_gateway_type: null,
    topology: null,
    auth_config: {},
    status: 'online',
    enabled: true,
    visibility: null,
    last_health_check: new Date().toISOString(),
    health_details: {
      uptime_seconds: 7200,
      routes_count: 5,
      policies_count: 2,
      discovered_apis_count: 3,
      discovered_apis: [],
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
        desired_state: { api_name: 'Payments API', api_version: '1.0.0' },
        sync_status: 'synced',
        gateway_environment: 'dev',
        api_catalog_id: 'payments',
      },
      {
        id: 'dep-2',
        desired_state: { api_name: 'Users API', api_version: '2.1.0' },
        sync_status: 'pending',
        gateway_environment: 'dev',
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
  mockOverview: {
    schema_version: '1.0',
    generated_at: '2026-05-06T06:00:00Z',
    gateway: {
      id: 'gw-1',
      name: 'stoa-gateway-edge-mcp-dev',
      display_name: 'STOA Edge MCP Gateway',
      gateway_type: 'stoa_edge_mcp',
      environment: 'dev',
      status: 'online',
      mode: 'edge-mcp',
      version: '0.9.1',
    },
    visibility: {
      rbac_scope: 'admin',
      tenant_id: null,
      filtered: false,
    },
    source: {
      control_plane_revision: 'abc123',
      last_loaded_at: '2026-05-06T05:58:00Z',
    },
    summary: {
      sync_status: 'in_sync',
      runtime_status: 'healthy',
      metrics_status: 'partial',
      apis_count: 2,
      expected_routes_count: 5,
      reported_routes_count: 5,
      effective_policies_count: 2,
      reported_policies_count: 2,
      failed_policies_count: 0,
    },
    resolved_config: {
      apis: [
        {
          tenant_id: 'tenant-a',
          api_id: 'payments-api',
          api_catalog_id: 'catalog-payments',
          name: 'Payments API',
          version: '1.0.0',
          source: {
            git_path: 'apis/payments/openapi.yaml',
            git_commit_sha: 'abc123',
            spec_hash: 'sha256:payments',
          },
          routes_count: 2,
          routes_preview: [
            { method: 'GET', path: '/v1/payments', backend: 'https://payments.internal' },
            { method: 'POST', path: '/v1/payments', backend: 'https://payments.internal' },
          ],
          backend: 'https://payments.internal',
          policies_count: 1,
          sync_status: 'in_sync',
          last_sync_at: '2026-05-06T05:59:00Z',
          last_error: null,
        },
        {
          tenant_id: 'tenant-a',
          api_id: 'users-api',
          api_catalog_id: 'catalog-users',
          name: 'Users API',
          version: '2.1.0',
          source: {
            git_path: 'apis/users/openapi.yaml',
            git_commit_sha: 'abc123',
            spec_hash: 'sha256:users',
          },
          routes_count: 3,
          routes_preview: [{ method: 'GET', path: '/v1/users', backend: 'https://users.internal' }],
          backend: 'https://users.internal',
          policies_count: 1,
          sync_status: 'pending',
          last_sync_at: null,
          last_error: null,
        },
      ],
      policies: [
        {
          id: 'policy-1',
          name: 'default-rate-limit',
          type: 'rate_limit',
          scope: 'gateway',
          target: { type: 'gateway', id: 'gw-1', name: 'STOA Edge MCP Gateway' },
          enabled: true,
          priority: 100,
          summary: 'Rate limit: 1000 req/min per consumer',
          sync_status: 'in_sync',
          source_binding: { id: 'binding-1', scope: 'gateway', target_id: 'gw-1' },
        },
        {
          id: 'policy-2',
          name: 'jwt-auth',
          type: 'jwt_validation',
          scope: 'api',
          target: { type: 'api', id: 'catalog-users', name: 'Users API' },
          enabled: true,
          priority: 10,
          summary: 'JWT policy configured',
          sync_status: 'pending',
          source_binding: { id: 'binding-2', scope: 'api', target_id: 'catalog-users' },
        },
      ],
    },
    sync: {
      desired_generation: 42,
      applied_generation: 42,
      status: 'in_sync',
      drift: false,
      last_reconciled_at: '2026-05-06T05:59:00Z',
      last_error: null,
      steps: [],
    },
    runtime: {
      status: 'healthy',
      last_heartbeat_at: '2026-05-06T05:59:42Z',
      heartbeat_age_seconds: 18,
      version: '0.9.1',
      mode: 'edge-mcp',
      uptime_seconds: 7200,
      reported_routes_count: 5,
      reported_policies_count: 2,
      mcp_tools_count: 3,
      requests_total: 129,
      error_rate: 0.01,
      memory_usage_bytes: 268435456,
    },
    data_quality: {
      runtime_freshness: 'fresh',
      heartbeat_stale_after_seconds: 90,
      metrics_status: 'partial',
      metrics_window_seconds: 300,
      warnings: [
        {
          code: 'runtime_metrics_partial',
          severity: 'info',
          message: 'Some runtime metrics are not available for this gateway',
        },
      ],
    },
  },
}));

const mockConfirm = vi.fn().mockResolvedValue(true);

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayInstance: vi.fn().mockResolvedValue(mockGateway),
    getGatewayOverview: vi.fn().mockResolvedValue(mockOverview),
    getGatewayDeployments: vi.fn().mockResolvedValue(mockDeployments),
    getGatewayTools: vi.fn().mockResolvedValue(mockTools),
    updateGatewayInstance: vi.fn().mockResolvedValue(mockGateway),
    checkGatewayHealth: vi.fn().mockResolvedValue({ status: 'ok' }),
    forceSyncDeployment: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="skeleton">Loading...</div>,
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [mockConfirm, () => null],
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

function cloneOverview() {
  return structuredClone(mockOverview);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GatewayDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    // Reset gateway to enabled state
    mockGateway.name = 'stoa-gateway-edge-mcp-dev';
    mockGateway.display_name = 'STOA Edge MCP Gateway';
    mockGateway.enabled = true;
    mockGateway.visibility = null;
    mockGateway.public_url = 'https://mcp.gostoa.dev';
    mockGateway.target_gateway_url = null;
    mockGateway.ui_url = null;
    mockGateway.endpoints = null;
    mockGateway.deployment_mode = null;
    mockGateway.target_gateway_type = null;
    mockGateway.topology = null;
    mockGateway.mode = 'edge-mcp';
    mockGateway.gateway_type = 'stoa_edge_mcp';
    mockGateway.health_details.discovered_apis_count = 3;
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

  it('renders endpoint-map URLs for a remote WebMethods link', async () => {
    const { apiService } = await import('../../services/api');
    vi.mocked(apiService.getGatewayInstance).mockResolvedValueOnce({
      ...mockGateway,
      id: 'gw-link',
      name: 'stoa-link-wm-staging',
      display_name: 'STOA Link webMethods Staging',
      gateway_type: 'stoa',
      base_url: 'http://stoa-link-wm-staging:8080',
      public_url: null,
      target_gateway_url: null,
      ui_url: null,
      endpoints: {
        publicUrl: 'https://staging-wm-k3s.gostoa.dev',
        targetGatewayUrl: 'https://staging-wm.gostoa.dev',
        uiUrl: 'https://staging-wm-ui.gostoa.dev',
      },
      mode: 'sidecar',
      deployment_mode: 'connect',
      target_gateway_type: 'webmethods',
      topology: 'remote-agent',
      tags: ['remote-agent', 'webmethods', 'not-a-k8s-sidecar'],
    });

    renderGatewayDetail('gw-link');
    await screen.findByText('STOA Link webMethods Staging');

    expect(screen.getByText('Link K8s')).toBeInTheDocument();
    expect(screen.getByText('Remote link')).toBeInTheDocument();
    expect(screen.getByText('STOA Runtime')).toBeInTheDocument();
    expect(screen.getByText('Target Gateway')).toBeInTheDocument();
    expect(screen.getByText('Third-party UI')).toBeInTheDocument();
    expect(screen.getByText('Open Gateway').closest('a')).toHaveAttribute(
      'href',
      'https://staging-wm-k3s.gostoa.dev'
    );
    expect(screen.getByText('https://staging-wm-k3s.gostoa.dev').closest('a')).toHaveAttribute(
      'href',
      'https://staging-wm-k3s.gostoa.dev'
    );
    expect(screen.getByText('https://staging-wm.gostoa.dev').closest('a')).toHaveAttribute(
      'href',
      'https://staging-wm.gostoa.dev'
    );
    expect(screen.getByText('https://staging-wm-ui.gostoa.dev').closest('a')).toHaveAttribute(
      'href',
      'https://staging-wm-ui.gostoa.dev'
    );
  });

  it('renders STOA sidecar runtime mode instead of remote-agent deployment mode', async () => {
    const { apiService } = await import('../../services/api');
    vi.mocked(apiService.getGatewayInstance).mockResolvedValueOnce({
      ...mockGateway,
      id: 'gw-sidecar',
      name: 'stoa-link-wm-dev-sidecar-dev',
      display_name: 'STOA Gateway (sidecar)',
      gateway_type: 'stoa_sidecar',
      base_url: 'https://dev-wm-k3s.gostoa.dev',
      public_url: 'https://dev-wm-k3s.gostoa.dev',
      target_gateway_url: 'https://dev-wm.gostoa.dev',
      ui_url: 'https://dev-wm.gostoa.dev/apigatewayui/',
      endpoints: {
        public_url: 'https://dev-wm-k3s.gostoa.dev',
        target_gateway_url: 'https://dev-wm.gostoa.dev',
        ui_url: 'https://dev-wm.gostoa.dev/apigatewayui/',
      },
      mode: 'sidecar',
      deployment_mode: 'connect',
      target_gateway_type: 'webmethods',
      topology: 'remote-agent',
      tags: ['mode:sidecar', 'auto-registered'],
    });

    renderGatewayDetail('gw-sidecar');
    await screen.findByText('STOA Gateway (sidecar)');

    expect(screen.getByText('Deployment Mode')).toBeInTheDocument();
    expect(screen.getByText('sidecar')).toBeInTheDocument();
    expect(screen.queryByText('connect')).not.toBeInTheDocument();
  });

  it('loads the gateway overview read-model', async () => {
    const { apiService } = await import('../../services/api');
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(apiService.getGatewayOverview).toHaveBeenCalledWith('gw-1');
  });

  it('renders overview summary cards', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('42 desired / 42 applied')).toBeInTheDocument();
    expect(screen.getByText('Heartbeat 18s ago')).toBeInTheDocument();
    expect(screen.getByText('2 deployed')).toBeInTheDocument();
    expect(screen.getByText('Routes 5 expected / 5 reported')).toBeInTheDocument();
    expect(screen.getByText('2 effective')).toBeInTheDocument();
    expect(screen.getByText('0 failed')).toBeInTheDocument();
    expect(
      screen.getByText('Some runtime metrics are not available for this gateway')
    ).toBeInTheDocument();
  });

  it('uses deployed APIs label for native sidecar gateways', async () => {
    mockGateway.mode = 'sidecar';
    mockGateway.gateway_type = 'stoa_sidecar';
    mockGateway.display_name = 'STOA Gateway (sidecar)';
    mockGateway.health_details.discovered_apis_count = 15;

    renderGatewayDetail();
    await screen.findByText('STOA Gateway (sidecar)');

    expect(screen.getByText('2 deployed')).toBeInTheDocument();
    expect(screen.queryByText('Discovered APIs')).not.toBeInTheDocument();
  });

  it('keeps the legacy Discovered APIs metric when overview is unavailable', async () => {
    const { apiService } = await import('../../services/api');
    vi.mocked(apiService.getGatewayOverview).mockRejectedValueOnce(
      new Error('overview unavailable')
    );
    mockGateway.mode = 'connect';
    mockGateway.gateway_type = 'webmethods';
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(
      screen.getByText('Gateway overview unavailable. Showing legacy gateway data.')
    ).toBeInTheDocument();
    expect(screen.getByText('Discovered APIs')).toBeInTheDocument();
  });

  it('renders overview APIs table with API detail links', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    const paymentsLink = screen.getByText('Payments API').closest('a');
    expect(paymentsLink).toHaveAttribute('href', '/apis/tenant-a/payments-api');
    expect(screen.getByText('Users API')).toBeInTheDocument();
    expect(screen.getAllByText('/v1/payments').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('/v1/users')).toBeInTheDocument();
    expect(screen.getByText('https://payments.internal')).toBeInTheDocument();
  });

  it('renders overview sync status badges', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getAllByText('in sync').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('pending')).toBeInTheDocument();
  });

  it('renders policies tab with safe summaries', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(screen.getByRole('button', { name: /Policies/ }));
    expect(screen.getByText('default-rate-limit')).toBeInTheDocument();
    expect(screen.getByText('Rate limit: 1000 req/min per consumer')).toBeInTheDocument();
    expect(screen.getByText('jwt-auth')).toBeInTheDocument();
    expect(screen.getByText('JWT policy configured')).toBeInTheDocument();
  });

  it('renders runtime tab with observed runtime and sync details', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(screen.getByRole('button', { name: /Runtime/ }));
    expect(screen.getByText('2h 0m')).toBeInTheDocument();
    expect(screen.getByText('1.0%')).toBeInTheDocument();
    expect(screen.getByText('256.0 MB')).toBeInTheDocument();
    expect(screen.getByText('129')).toBeInTheDocument();
    expect(screen.getByText('partial / 300s')).toBeInTheDocument();
    expect(screen.getByText('5 expected / 5 reported')).toBeInTheDocument();
  });

  it('renders RBAC filtered overview notice', async () => {
    const { apiService } = await import('../../services/api');
    const overview = cloneOverview();
    overview.visibility = { rbac_scope: 'tenant', tenant_id: 'tenant-a', filtered: true };
    vi.mocked(apiService.getGatewayOverview).mockResolvedValueOnce(overview);
    renderGatewayDetail();
    expect(await screen.findByText('Vue filtrée selon vos permissions.')).toBeInTheDocument();
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
    expect(screen.getByRole('heading', { name: /MCP Tools/ })).toBeInTheDocument();
  });

  it('renders empty state when no deployments and no tools', async () => {
    const { apiService } = await import('../../services/api');
    const overview = cloneOverview();
    overview.summary.apis_count = 0;
    overview.summary.expected_routes_count = 0;
    overview.summary.reported_routes_count = 0;
    overview.summary.effective_policies_count = 0;
    overview.summary.reported_policies_count = 0;
    overview.resolved_config.apis = [];
    overview.resolved_config.policies = [];
    vi.mocked(apiService.getGatewayOverview).mockResolvedValueOnce(overview);
    vi.mocked(apiService.getGatewayTools).mockResolvedValueOnce([]);
    vi.mocked(apiService.getGatewayDeployments).mockResolvedValueOnce({
      items: [],
      total: 0,
    });
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('No APIs are deployed on this gateway.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Policies/ }));
    expect(
      screen.getByText('No effective policies are applied to this gateway.')
    ).toBeInTheDocument();
  });

  it('shows both deployed and tools sections when both have data', async () => {
    renderGatewayDetail();
    expect(await screen.findByText('weather_forecast')).toBeInTheDocument();
    expect(screen.getByText('Payments API')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /APIs/ })).toBeInTheDocument();
    expect(screen.queryByText('API Deployments')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /MCP Tools/ })).toBeInTheDocument();
  });

  // --- Enabled/Disabled ---

  it('shows Disable button when gateway is enabled', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('Disable')).toBeInTheDocument();
  });

  it('shows Enable button and Disabled badge when gateway is disabled', async () => {
    mockGateway.enabled = false;
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('Enable')).toBeInTheDocument();
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });

  it('shows disabled banner when gateway is disabled', async () => {
    mockGateway.enabled = false;
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('Gateway disabled')).toBeInTheDocument();
  });

  it('confirms before disabling gateway', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(screen.getByText('Disable'));
    await waitFor(() => {
      expect(mockConfirm).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Disable Gateway',
          variant: 'danger',
        })
      );
    });
  });

  it('calls updateGatewayInstance with enabled=false on disable confirm', async () => {
    const { apiService } = await import('../../services/api');
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(screen.getByText('Disable'));
    await waitFor(() => {
      expect(apiService.updateGatewayInstance).toHaveBeenCalledWith('gw-1', { enabled: false });
    });
  });

  it('enables gateway without confirmation', async () => {
    mockGateway.enabled = false;
    const { apiService } = await import('../../services/api');
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(screen.getByText('Enable'));
    await waitFor(() => {
      expect(apiService.updateGatewayInstance).toHaveBeenCalledWith('gw-1', { enabled: true });
    });
    // Should NOT show confirm dialog for enable
    expect(mockConfirm).not.toHaveBeenCalled();
  });

  // --- Visibility ---

  it('shows "All tenants" when visibility is null', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('All tenants')).toBeInTheDocument();
  });

  it('shows tenant IDs when visibility is restricted', async () => {
    mockGateway.visibility = { tenant_ids: ['tenant-a', 'tenant-b'] } as any;
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getAllByText('tenant-a').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('tenant-b')).toBeInTheDocument();
  });

  // --- Actions ---

  it('renders Health Check button for admin', async () => {
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.getByText('Health Check')).toBeInTheDocument();
  });

  it('calls checkGatewayHealth on Health Check click', async () => {
    const { apiService } = await import('../../services/api');
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    fireEvent.click(screen.getByText('Health Check'));
    await waitFor(() => {
      expect(apiService.checkGatewayHealth).toHaveBeenCalledWith('gw-1');
    });
  });

  it('renders force sync buttons for deployments', async () => {
    const { apiService } = await import('../../services/api');
    vi.mocked(apiService.getGatewayOverview).mockRejectedValueOnce(
      new Error('overview unavailable')
    );
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    const syncButtons = screen.getAllByText('Sync');
    expect(syncButtons.length).toBe(2); // one per deployment
  });

  it('calls forceSyncDeployment on sync click', async () => {
    const { apiService } = await import('../../services/api');
    vi.mocked(apiService.getGatewayOverview).mockRejectedValueOnce(
      new Error('overview unavailable')
    );
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    const syncButtons = screen.getAllByText('Sync');
    fireEvent.click(syncButtons[0]);
    await waitFor(() => {
      expect(apiService.forceSyncDeployment).toHaveBeenCalledWith('dep-1');
    });
  });

  // --- RBAC ---

  it('hides action buttons for viewer role', async () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
    renderGatewayDetail();
    await screen.findByText('STOA Edge MCP Gateway');
    expect(screen.queryByText('Disable')).not.toBeInTheDocument();
    expect(screen.queryByText('Health Check')).not.toBeInTheDocument();
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
