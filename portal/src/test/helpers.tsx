/**
 * Shared Test Helpers for Portal Functional Tests (CAB-1133)
 *
 * Provides reusable factories, wrappers, and mock data for page-level tests.
 */

import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { type ReactElement, type ReactNode } from 'react';
import { vi } from 'vitest';
import type { User } from '../types';

// ============ Role-based Permissions & Scopes ============

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
    'apis:promote',
    'apps:create',
    'apps:read',
    'apps:update',
    'apps:delete',
    'users:manage',
    'audit:read',
  ],
  'tenant-admin': [
    'tenants:read',
    'apis:create',
    'apis:read',
    'apis:update',
    'apis:delete',
    'apis:deploy',
    'apis:promote',
    'apps:create',
    'apps:read',
    'apps:update',
    'apps:delete',
    'users:manage',
    'audit:read',
  ],
  devops: [
    'tenants:read',
    'apis:create',
    'apis:read',
    'apis:update',
    'apis:deploy',
    'apis:promote',
    'apps:create',
    'apps:read',
    'apps:update',
    'audit:read',
  ],
  viewer: ['tenants:read', 'apis:read', 'apps:read', 'audit:read'],
};

const ROLE_SCOPES: Record<string, string[]> = {
  'cpi-admin': [
    'stoa:platform:read',
    'stoa:platform:write',
    'stoa:catalog:read',
    'stoa:catalog:write',
    'stoa:subscriptions:read',
    'stoa:subscriptions:write',
    'stoa:metrics:read',
    'stoa:logs:full',
    'stoa:security:read',
    'stoa:security:write',
    'stoa:tools:read',
    'stoa:tools:execute',
  ],
  'tenant-admin': [
    'stoa:catalog:read',
    'stoa:catalog:write',
    'stoa:subscriptions:read',
    'stoa:subscriptions:write',
    'stoa:metrics:read',
    'stoa:logs:functional',
    'stoa:tools:read',
    'stoa:tools:execute',
  ],
  devops: [
    'stoa:catalog:read',
    'stoa:catalog:write',
    'stoa:subscriptions:read',
    'stoa:metrics:read',
    'stoa:logs:technical',
    'stoa:tools:read',
    'stoa:tools:execute',
  ],
  viewer: ['stoa:catalog:read', 'stoa:subscriptions:read', 'stoa:metrics:read', 'stoa:tools:read'],
};

// ============ Persona Factories ============

export type PersonaRole = 'cpi-admin' | 'tenant-admin' | 'devops' | 'viewer';

const PERSONA_USERS: Record<PersonaRole, User> = {
  'cpi-admin': {
    id: 'user-halliday',
    email: 'halliday@gregarious-games.com',
    name: 'James Halliday',
    tenant_id: 'gregarious-games',
    organization: 'Gregarious Games',
    roles: ['cpi-admin'],
    permissions: ROLE_PERMISSIONS['cpi-admin'],
    effective_scopes: ROLE_SCOPES['cpi-admin'],
    is_admin: true,
  },
  'tenant-admin': {
    id: 'user-parzival',
    email: 'parzival@oasis-gunters.com',
    name: 'Wade Watts',
    tenant_id: 'oasis-gunters',
    organization: 'OASIS Gunters',
    roles: ['tenant-admin'],
    permissions: ROLE_PERMISSIONS['tenant-admin'],
    effective_scopes: ROLE_SCOPES['tenant-admin'],
    is_admin: false,
  },
  devops: {
    id: 'user-art3mis',
    email: 'art3mis@oasis-gunters.com',
    name: 'Samantha Cook',
    tenant_id: 'oasis-gunters',
    organization: 'OASIS Gunters',
    roles: ['devops'],
    permissions: ROLE_PERMISSIONS['devops'],
    effective_scopes: ROLE_SCOPES['devops'],
    is_admin: false,
  },
  viewer: {
    id: 'user-aech',
    email: 'aech@oasis-gunters.com',
    name: 'Helen Harris',
    tenant_id: 'oasis-gunters',
    organization: 'OASIS Gunters',
    roles: ['viewer'],
    permissions: ROLE_PERMISSIONS['viewer'],
    effective_scopes: ROLE_SCOPES['viewer'],
    is_admin: false,
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
    accessToken: `mock-token-${role}`,
    hasPermission: (permission: string) => user.permissions.includes(permission),
    hasAnyPermission: (permissions: string[]) =>
      permissions.some((p) => user.permissions.includes(p)),
    hasAllPermissions: (permissions: string[]) =>
      permissions.every((p) => user.permissions.includes(p)),
    hasRole: (r: string) => user.roles.includes(r),
    hasScope: (scope: string) => user.effective_scopes.includes(scope),
    login: vi.fn(),
    logout: vi.fn(),
    refreshPermissions: vi.fn().mockResolvedValue(undefined),
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

export const mockAPI = (overrides: Record<string, unknown> = {}) => ({
  id: 'api-1',
  name: 'Payment API',
  version: '2.1.0',
  description: 'Process payments securely',
  category: 'Finance',
  tags: ['payments', 'fintech'],
  tenantId: 'oasis-gunters',
  tenantName: 'OASIS Gunters',
  status: 'published' as const,
  endpoints: [
    {
      path: '/v1/payments',
      method: 'POST' as const,
      summary: 'Create payment',
      parameters: [],
      responses: { '200': { description: 'Payment created' } },
    },
    {
      path: '/v1/payments/{id}',
      method: 'GET' as const,
      summary: 'Get payment',
      parameters: [{ name: 'id', in: 'path' as const, required: true, description: 'Payment ID' }],
      responses: { '200': { description: 'Payment details' } },
    },
  ],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockApplication = (overrides: Record<string, unknown> = {}) => ({
  id: 'app-1',
  name: 'My App',
  description: 'Test application',
  clientId: 'client-abc123',
  callbackUrls: ['https://app.example.com/callback'],
  userId: 'user-parzival',
  status: 'active' as const,
  subscriptions: [],
  createdAt: '2026-01-15T00:00:00Z',
  updatedAt: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockMCPServer = (overrides: Record<string, unknown> = {}) => ({
  id: 'server-1',
  name: 'stoa-platform',
  displayName: 'STOA Platform Tools',
  description: 'Core STOA administration tools',
  icon: 'settings',
  category: 'platform' as const,
  tenant_id: undefined,
  visibility: { roles: ['cpi-admin', 'tenant-admin', 'devops'], public: false },
  tools: [
    {
      id: 'tool-1',
      name: 'list-apis',
      displayName: 'List APIs',
      description: 'List all registered APIs',
      enabled: true,
      requires_approval: false,
    },
    {
      id: 'tool-2',
      name: 'create-api',
      displayName: 'Create API',
      description: 'Register a new API',
      enabled: true,
      requires_approval: true,
    },
  ],
  status: 'active' as const,
  version: '1.0.0',
  documentation_url: 'https://docs.gostoa.dev/tools',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockContract = (overrides: Record<string, unknown> = {}) => ({
  id: 'contract-1',
  tenant_id: 'oasis-gunters',
  name: 'orders-api',
  display_name: 'Orders API',
  description: 'Order management service',
  version: '1.0.0',
  status: 'published' as const,
  openapi_spec_url: 'https://api.example.com/openapi.json',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  created_by: 'user-parzival',
  bindings: [
    { protocol: 'rest' as const, enabled: true, endpoint: '/v1/orders' },
    { protocol: 'mcp' as const, enabled: true, tool_name: 'orders-api' },
    { protocol: 'graphql' as const, enabled: false },
    { protocol: 'grpc' as const, enabled: false },
    { protocol: 'kafka' as const, enabled: false },
  ],
  ...overrides,
});

export const mockWebhook = (overrides: Record<string, unknown> = {}) => ({
  id: 'wh-1',
  tenant_id: 'oasis-gunters',
  name: 'Slack Notifications',
  url: 'https://hooks.slack.com/services/T00/B00/xxx',
  events: ['subscription.created', 'subscription.approved'] as const,
  has_secret: true,
  headers: {},
  enabled: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockConsumer = (overrides: Record<string, unknown> = {}) => ({
  id: 'consumer-1',
  external_id: 'my-app-01',
  name: 'My App',
  email: 'dev@company.com',
  company: 'Acme Corp',
  description: 'Test consumer',
  tenant_id: 'oasis-gunters',
  status: 'active' as const,
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
  ...overrides,
});

export const mockDashboardStats = () => ({
  tools_available: 12,
  active_subscriptions: 5,
  api_calls_this_week: 2450,
});

export const mockDashboardActivity = () => [
  {
    id: 'a1',
    type: 'subscription.created' as const,
    title: 'New subscription',
    description: 'Subscribed to Payment API',
    tool_id: 'tool-1',
    timestamp: '2026-02-10T10:00:00Z',
  },
  {
    id: 'a2',
    type: 'api.call' as const,
    title: 'API Call',
    description: 'Called list-apis',
    tool_id: 'tool-1',
    timestamp: '2026-02-10T09:30:00Z',
  },
];

export const mockUsageSummary = () => ({
  tenant_id: 'oasis-gunters',
  user_id: 'user-parzival',
  today: {
    period: 'today',
    total_calls: 150,
    success_count: 142,
    error_count: 8,
    success_rate: 94.7,
    avg_latency_ms: 185,
  },
  this_week: {
    period: 'week',
    total_calls: 1200,
    success_count: 1150,
    error_count: 50,
    success_rate: 95.8,
    avg_latency_ms: 175,
  },
  this_month: {
    period: 'month',
    total_calls: 4500,
    success_count: 4350,
    error_count: 150,
    success_rate: 96.7,
    avg_latency_ms: 190,
  },
  top_tools: [
    {
      tool_id: 'tool-1',
      tool_name: 'list-apis',
      call_count: 500,
      success_rate: 99.0,
      avg_latency_ms: 120,
    },
    {
      tool_id: 'tool-2',
      tool_name: 'create-api',
      call_count: 300,
      success_rate: 97.5,
      avg_latency_ms: 200,
    },
  ],
  daily_calls: [
    { date: '2026-02-04', calls: 180 },
    { date: '2026-02-05', calls: 220 },
    { date: '2026-02-06', calls: 190 },
    { date: '2026-02-07', calls: 250 },
    { date: '2026-02-08', calls: 160 },
    { date: '2026-02-09', calls: 200 },
    { date: '2026-02-10', calls: 150 },
  ],
});

export const mockServerSubscription = (overrides: Record<string, unknown> = {}) => ({
  id: 'sub-1',
  server_id: 'server-1',
  server: mockMCPServer(),
  tenant_id: 'oasis-gunters',
  user_id: 'user-parzival',
  status: 'active' as const,
  plan: 'free' as const,
  tool_access: [
    { tool_id: 'tool-1', tool_name: 'list-apis', status: 'enabled' as const },
    { tool_id: 'tool-2', tool_name: 'create-api', status: 'pending_approval' as const },
  ],
  api_key_prefix: 'stoa_sk_abc1',
  created_at: '2026-01-20T00:00:00Z',
  ...overrides,
});
