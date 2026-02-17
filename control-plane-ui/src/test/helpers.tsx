/**
 * Shared Test Helpers for Console Functional Tests (CAB-1134)
 *
 * Provides reusable persona factories, render wrappers, and mock data.
 * Pattern adapted from portal/src/test/helpers.tsx for Console specifics.
 */

import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { type ReactElement, type ReactNode } from 'react';
import { vi } from 'vitest';
import type {
  User,
  Role,
  Tenant,
  API,
  Application,
  Deployment,
  GatewayInstance,
  GatewayDeployment,
  ExternalMCPServer,
  BackendApi,
  SaasApiKey,
} from '../types';

// ============ Role-based Permissions (mirrors AuthContext.tsx L31-71) ============

const ROLE_PERMISSIONS: Record<string, string[]> = {
  'cpi-admin': [
    'tenants:create',
    'tenants:read',
    'tenants:update',
    'tenants:delete',
    'apis:create',
    'apis:read',
    'apis:update',
    'apis:delete',
    'apis:deploy',
    'apps:create',
    'apps:read',
    'apps:update',
    'apps:delete',
    'users:create',
    'users:read',
    'users:update',
    'users:delete',
    'audit:read',
    'admin:servers',
    'workflows:read',
    'workflows:manage',
  ],
  'tenant-admin': [
    'apis:create',
    'apis:read',
    'apis:update',
    'apis:delete',
    'apis:deploy',
    'apps:create',
    'apps:read',
    'apps:update',
    'apps:delete',
    'users:create',
    'users:read',
    'users:update',
    'audit:read',
    'admin:servers',
    'workflows:read',
    'workflows:manage',
  ],
  devops: [
    'apis:create',
    'apis:read',
    'apis:update',
    'apis:deploy',
    'apps:read',
    'audit:read',
    'workflows:read',
  ],
  viewer: ['apis:read', 'apps:read', 'audit:read', 'workflows:read'],
};

// ============ Persona Factories ============

export type PersonaRole = Role;

const PERSONA_USERS: Record<PersonaRole, User> = {
  'cpi-admin': {
    id: 'user-halliday',
    email: 'halliday@gregarious-games.com',
    name: 'James Halliday',
    tenant_id: 'gregarious-games',
    roles: ['cpi-admin'],
    permissions: ROLE_PERMISSIONS['cpi-admin'],
  },
  'tenant-admin': {
    id: 'user-parzival',
    email: 'parzival@oasis-gunters.com',
    name: 'Wade Watts',
    tenant_id: 'oasis-gunters',
    roles: ['tenant-admin'],
    permissions: ROLE_PERMISSIONS['tenant-admin'],
  },
  devops: {
    id: 'user-art3mis',
    email: 'art3mis@oasis-gunters.com',
    name: 'Samantha Cook',
    tenant_id: 'oasis-gunters',
    roles: ['devops'],
    permissions: ROLE_PERMISSIONS['devops'],
  },
  viewer: {
    id: 'user-aech',
    email: 'aech@oasis-gunters.com',
    name: 'Helen Harris',
    tenant_id: 'oasis-gunters',
    roles: ['viewer'],
    permissions: ROLE_PERMISSIONS['viewer'],
  },
};

/** Get a mock user for a given persona role */
export function createMockUser(role: PersonaRole): User {
  return { ...PERSONA_USERS[role] };
}

/** Build a full useAuth() mock return value for a persona */
export function createAuthMock(role: PersonaRole) {
  const user = createMockUser(role);
  return {
    user,
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    login: vi.fn(),
    logout: vi.fn(),
    hasPermission: (permission: string) => user.permissions.includes(permission),
    hasRole: (r: string) => user.roles.includes(r),
  };
}

// ============ Render Wrapper ============

interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  route?: string;
  queryClient?: QueryClient;
}

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

/**
 * Render a component wrapped in QueryClientProvider + MemoryRouter.
 * AuthContext is NOT included — mock it via vi.mock() at the test file level.
 */
export function renderWithProviders(
  ui: ReactElement,
  { route = '/', queryClient, ...renderOptions }: RenderWithProvidersOptions = {}
) {
  const testQueryClient = queryClient ?? createTestQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient: testQueryClient,
  };
}

// ============ Mock Data Factories ============

export const mockTenant = (overrides: Partial<Tenant> = {}): Tenant => ({
  id: 'tenant-1',
  name: 'oasis-gunters',
  display_name: 'OASIS Gunters',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockAPI = (overrides: Partial<API> = {}): API => ({
  id: 'api-1',
  tenant_id: 'oasis-gunters',
  name: 'payment-api',
  display_name: 'Payment API',
  version: '1.0.0',
  description: 'Process payments securely',
  backend_url: 'https://api.example.com/v1',
  status: 'published',
  deployed_dev: true,
  deployed_staging: false,
  tags: ['payments'],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockApplication = (overrides: Partial<Application> = {}): Application => ({
  id: 'app-1',
  tenant_id: 'oasis-gunters',
  name: 'my-app',
  display_name: 'My App',
  description: 'Test application',
  client_id: 'client-abc123',
  status: 'approved',
  api_subscriptions: [],
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockGatewayInstance = (overrides: Partial<GatewayInstance> = {}): GatewayInstance => ({
  id: 'gw-1',
  name: 'stoa-edge-mcp-1',
  display_name: 'STOA Edge MCP Gateway',
  gateway_type: 'stoa_edge_mcp',
  environment: 'dev',
  base_url: 'https://mcp.gostoa.dev',
  auth_config: {},
  status: 'online',
  capabilities: ['mcp', 'openapi'],
  tags: ['production'],
  mode: 'edge-mcp',
  version: '0.1.0',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockGatewayDeployment = (
  overrides: Partial<GatewayDeployment> = {}
): GatewayDeployment => ({
  id: 'deploy-1',
  api_catalog_id: 'api-1',
  gateway_instance_id: 'gw-1',
  desired_state: {},
  desired_at: '2026-02-01T00:00:00Z',
  sync_status: 'synced',
  sync_attempts: 1,
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockExternalMCPServer = (
  overrides: Partial<ExternalMCPServer> = {}
): ExternalMCPServer => ({
  id: 'srv-1',
  name: 'linear-mcp',
  display_name: 'Linear',
  description: 'Linear project management tools',
  base_url: 'https://mcp.linear.app',
  transport: 'sse',
  auth_type: 'bearer_token',
  enabled: true,
  health_status: 'healthy',
  tools_count: 12,
  tool_prefix: 'linear',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockBackendApi = (overrides: Partial<BackendApi> = {}): BackendApi => ({
  id: 'bapi-1',
  tenant_id: 'oasis-gunters',
  name: 'petstore-api',
  display_name: 'Petstore API',
  description: 'Sample Petstore backend',
  backend_url: 'https://petstore.swagger.io/v2',
  openapi_spec_url: 'https://petstore.swagger.io/v2/swagger.json',
  auth_type: 'api_key',
  has_credentials: true,
  status: 'active',
  tool_count: 5,
  spec_hash: 'abc123',
  last_synced_at: '2026-02-10T00:00:00Z',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  created_by: 'user-parzival',
  ...overrides,
});

export const mockDeployment = (overrides: Partial<Deployment> = {}): Deployment => ({
  id: 'deploy-1',
  tenant_id: 'oasis-gunters',
  api_id: 'api-1',
  api_name: 'Payment API',
  environment: 'dev',
  version: '1.0.0',
  status: 'success',
  deployed_by: 'user-parzival',
  created_at: '2026-02-15T10:00:00Z',
  updated_at: '2026-02-15T10:05:00Z',
  completed_at: '2026-02-15T10:05:00Z',
  attempt_count: 1,
  ...overrides,
});

export const mockSaasApiKey = (overrides: Partial<SaasApiKey> = {}): SaasApiKey => ({
  id: 'skey-1',
  tenant_id: 'oasis-gunters',
  name: 'my-agent-key',
  description: 'Key for AI agent access',
  key_prefix: 'stoa_saas_a1b2',
  allowed_backend_api_ids: ['bapi-1'],
  rate_limit_rpm: 60,
  status: 'active',
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  expires_at: '2026-08-01T00:00:00Z',
  last_used_at: '2026-02-14T10:30:00Z',
  created_by: 'user-parzival',
  ...overrides,
});
