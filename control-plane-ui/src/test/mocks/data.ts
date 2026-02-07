import type {
  Tenant, API, Application, Deployment, GatewayInstance,
  PlatformStatusResponse, ProspectListResponse, ProspectsMetricsResponse,
  AggregatedMetrics, User,
} from '../../types';
import type { BusinessMetrics } from '../../services/api';

// =========================================================================
// Users
// =========================================================================

export const mockAdminUser: User = {
  id: 'user-admin',
  email: 'parzival@oasis.gg',
  name: 'Parzival',
  roles: ['cpi-admin'],
  tenant_id: 'oasis-gunters',
  permissions: [
    'tenants:create', 'tenants:read', 'tenants:update', 'tenants:delete',
    'apis:create', 'apis:read', 'apis:update', 'apis:delete', 'apis:deploy',
    'apps:create', 'apps:read', 'apps:update', 'apps:delete',
    'users:create', 'users:read', 'users:update', 'users:delete',
    'audit:read', 'admin:servers',
  ],
};

export const mockViewerUser: User = {
  id: 'user-viewer',
  email: 'viewer@oasis.gg',
  name: 'Viewer',
  roles: ['viewer'],
  tenant_id: 'oasis-gunters',
  permissions: ['apis:read', 'apps:read', 'audit:read'],
};

// =========================================================================
// Tenants
// =========================================================================

export const mockTenants: Tenant[] = [
  { id: 'oasis-gunters', name: 'oasis-gunters', display_name: 'Oasis Gunters', status: 'active', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
  { id: 'ioi-sixers', name: 'ioi-sixers', display_name: 'IOI Sixers', status: 'active', created_at: '2024-01-02T00:00:00Z', updated_at: '2024-01-02T00:00:00Z' },
];

// =========================================================================
// APIs
// =========================================================================

export const mockApis: API[] = [
  {
    id: 'api-1', tenant_id: 'oasis-gunters', name: 'payment-api', display_name: 'Payment API',
    version: '1.0.0', description: 'Handles all payment processing', backend_url: 'https://payments.example.com',
    status: 'published', deployed_dev: true, deployed_staging: false, tags: ['payments', 'portal:published'],
    portal_promoted: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-15T00:00:00Z',
  },
  {
    id: 'api-2', tenant_id: 'oasis-gunters', name: 'user-api', display_name: 'User API',
    version: '2.0.0', description: 'User management service', backend_url: 'https://users.example.com',
    status: 'draft', deployed_dev: false, deployed_staging: false, tags: ['users'],
    created_at: '2024-01-05T00:00:00Z', updated_at: '2024-01-10T00:00:00Z',
  },
];

// =========================================================================
// Applications
// =========================================================================

export const mockApplications: Application[] = [
  {
    id: 'app-1', tenant_id: 'oasis-gunters', name: 'mobile-app', display_name: 'Mobile App',
    description: 'iOS/Android mobile application', client_id: 'client-abc123', status: 'approved',
    api_subscriptions: ['api-1'], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-15T00:00:00Z',
  },
  {
    id: 'app-2', tenant_id: 'oasis-gunters', name: 'web-app', display_name: 'Web Application',
    description: 'Main web application', client_id: 'client-def456', status: 'pending',
    api_subscriptions: [], created_at: '2024-01-10T00:00:00Z', updated_at: '2024-01-10T00:00:00Z',
  },
];

// =========================================================================
// Deployments
// =========================================================================

export const mockDeployments: Deployment[] = [
  {
    id: 'dep-1', tenant_id: 'oasis-gunters', api_id: 'api-1', api_name: 'Payment API',
    environment: 'dev', version: '1.0.0', status: 'success',
    started_at: '2024-01-15T10:00:00Z', completed_at: '2024-01-15T10:05:00Z',
    deployed_by: 'parzival',
  },
];

// =========================================================================
// Gateway Instances
// =========================================================================

export const mockGateways: GatewayInstance[] = [
  {
    id: 'gw-1', name: 'stoa-edge-mcp-1', display_name: 'STOA Edge MCP Gateway',
    gateway_type: 'stoa_edge_mcp', environment: 'dev', base_url: 'https://mcp.gostoa.dev',
    auth_config: {}, status: 'online', capabilities: ['mcp', 'openapi', 'rate_limiting'],
    tags: ['production'], mode: 'edge-mcp', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-15T00:00:00Z',
  },
  {
    id: 'gw-2', name: 'webmethods-prod', display_name: 'webMethods Production',
    gateway_type: 'webmethods', environment: 'prod', base_url: 'https://wm.example.com',
    auth_config: {}, status: 'degraded', capabilities: ['rest', 'soap'],
    tags: ['legacy'], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-10T00:00:00Z',
  },
];

// =========================================================================
// Platform Status
// =========================================================================

export const mockPlatformStatus: PlatformStatusResponse = {
  gitops: {
    status: 'healthy',
    components: [
      { name: 'control-plane-api', display_name: 'Control Plane API', sync_status: 'Synced', health_status: 'Healthy', revision: 'abc123', last_sync: '2024-01-15T10:00:00Z', message: null },
      { name: 'mcp-gateway', display_name: 'MCP Gateway', sync_status: 'Synced', health_status: 'Healthy', revision: 'def456', last_sync: '2024-01-15T10:00:00Z', message: null },
    ],
    checked_at: '2024-01-15T10:00:00Z',
  },
  events: [],
  external_links: { argocd: 'https://argocd.gostoa.dev', grafana: '/grafana/', prometheus: 'https://prometheus.gostoa.dev', logs: '/logs/' },
  timestamp: '2024-01-15T10:00:00Z',
};

// =========================================================================
// Gateway Observability Metrics
// =========================================================================

export const mockAggregatedMetrics: AggregatedMetrics = {
  health: { total_gateways: 5, online: 3, offline: 1, degraded: 1, maintenance: 0, health_percentage: 80 },
  sync: { total_deployments: 10, synced: 7, pending: 1, syncing: 1, drifted: 1, error: 0, deleting: 0, sync_percentage: 70 },
  overall_status: 'DEGRADED',
};

// =========================================================================
// Business Metrics
// =========================================================================

export const mockBusinessMetrics: BusinessMetrics = {
  active_tenants: 12, new_tenants_30d: 3, tenant_growth: 33.3,
  apdex_score: 0.92, total_tokens: 15000, total_calls: 5600,
};

// =========================================================================
// Admin Prospects
// =========================================================================

export const mockProspectsResponse: ProspectListResponse = {
  data: [
    { id: 'p-1', email: 'ceo@acme.com', company: 'Acme Corp', status: 'converted', source: 'website', created_at: '2024-01-01T00:00:00Z', opened_at: '2024-01-02T00:00:00Z', last_activity_at: '2024-01-10T00:00:00Z', time_to_first_tool_seconds: 120, nps_score: 9, nps_category: 'promoter', total_events: 15 },
    { id: 'p-2', email: 'dev@startup.io', company: 'Startup IO', status: 'opened', source: 'referral', created_at: '2024-01-05T00:00:00Z', opened_at: '2024-01-06T00:00:00Z', total_events: 5 },
  ],
  meta: { total: 2, page: 1, limit: 25 },
};

export const mockProspectsMetrics: ProspectsMetricsResponse = {
  total_invited: 50, total_active: 20, avg_time_to_tool: 95, avg_nps: 8.2,
  by_status: { total_invites: 50, pending: 10, opened: 15, converted: 20, expired: 5 },
  nps: { promoters: 12, passives: 5, detractors: 3, no_response: 30, nps_score: 45, avg_score: 8.2 },
  timing: { avg_time_to_open_seconds: 3600, avg_time_to_first_tool_seconds: 7200 },
  top_companies: [{ company: 'Acme Corp', invite_count: 5, converted_count: 3 }],
};
