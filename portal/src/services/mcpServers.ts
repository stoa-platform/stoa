/**
 * STOA Developer Portal - MCP Servers Service
 *
 * Service for managing MCP Server subscriptions with role-based visibility.
 * Servers are grouped collections of tools with unified subscription management.
 */

import { mcpClient } from './mcpClient';
import type {
  MCPServer,
  MCPServerSubscription,
  MCPServerSubscriptionCreate,
  MCPServerSubscriptionWithKey,
  User,
} from '../types';

/**
 * Check if a user can see a server based on visibility rules
 */
export function canUserSeeServer(server: MCPServer, user: User | null): boolean {
  if (!user) return false;

  const { visibility } = server;
  const userRoles = user.roles || [];

  // Public servers are visible to all authenticated users
  if (visibility.public) return true;

  // Check excluded roles first
  if (visibility.excludeRoles?.length) {
    const isExcluded = visibility.excludeRoles.some(role => userRoles.includes(role));
    if (isExcluded) return false;
  }

  // If roles are specified, user must have at least one
  if (visibility.roles?.length) {
    return visibility.roles.some(role => userRoles.includes(role));
  }

  // No specific visibility rules = visible to all
  return true;
}

/**
 * Filter servers based on user's roles
 */
export function filterServersByRole(servers: MCPServer[], user: User | null): MCPServer[] {
  return servers.filter(server => canUserSeeServer(server, user));
}

/**
 * Get all MCP Servers the user can see
 * GET /servers
 */
async function getServers(): Promise<MCPServer[]> {
  const response = await mcpClient.get<{ servers: MCPServer[] }>('/servers');
  return response.data.servers;
}

/**
 * Get servers filtered by user's roles (client-side filtering)
 * Backend should also filter, but this provides double protection
 */
async function getVisibleServers(user: User | null): Promise<MCPServer[]> {
  const servers = await getServers();
  return filterServersByRole(servers, user);
}

/**
 * Get a specific server by ID
 * GET /servers/{id}
 */
async function getServer(serverId: string): Promise<MCPServer> {
  const response = await mcpClient.get<MCPServer>(`/servers/${serverId}`);
  return response.data;
}

/**
 * Get user's server subscriptions
 * GET /server-subscriptions
 */
async function getMyServerSubscriptions(): Promise<MCPServerSubscription[]> {
  const response = await mcpClient.get<{ subscriptions: MCPServerSubscription[] }>('/server-subscriptions');
  return response.data.subscriptions;
}

/**
 * Get a specific server subscription
 * GET /server-subscriptions/{id}
 */
async function getServerSubscription(subscriptionId: string): Promise<MCPServerSubscription> {
  const response = await mcpClient.get<MCPServerSubscription>(`/server-subscriptions/${subscriptionId}`);
  return response.data;
}

/**
 * Subscribe to a server with selected tools
 * POST /server-subscriptions
 */
async function subscribeToServer(
  request: MCPServerSubscriptionCreate
): Promise<MCPServerSubscriptionWithKey> {
  const response = await mcpClient.post<MCPServerSubscriptionWithKey>('/server-subscriptions', request);
  return response.data;
}

/**
 * Update tool access within a subscription
 * PATCH /server-subscriptions/{id}/tools
 */
async function updateToolAccess(
  subscriptionId: string,
  toolIds: string[],
  action: 'enable' | 'disable' | 'request'
): Promise<MCPServerSubscription> {
  const response = await mcpClient.patch<MCPServerSubscription>(
    `/server-subscriptions/${subscriptionId}/tools`,
    { tool_ids: toolIds, action }
  );
  return response.data;
}

/**
 * Revoke a server subscription
 * DELETE /server-subscriptions/{id}
 */
async function revokeServerSubscription(subscriptionId: string): Promise<void> {
  await mcpClient.delete(`/server-subscriptions/${subscriptionId}`);
}

/**
 * Rotate API key for a server subscription
 * POST /server-subscriptions/{id}/rotate-key
 */
async function rotateServerKey(
  subscriptionId: string,
  gracePeriodHours: number = 24
): Promise<{
  new_api_key: string;
  old_key_expires_at: string;
}> {
  const response = await mcpClient.post(`/server-subscriptions/${subscriptionId}/rotate-key`, {
    grace_period_hours: gracePeriodHours,
  });
  return response.data;
}

/**
 * Get servers grouped by category
 */
async function getServersByCategory(user: User | null): Promise<{
  platform: MCPServer[];
  tenant: MCPServer[];
  public: MCPServer[];
}> {
  const servers = await getVisibleServers(user);

  return {
    platform: servers.filter(s => s.category === 'platform'),
    tenant: servers.filter(s => s.category === 'tenant'),
    public: servers.filter(s => s.category === 'public'),
  };
}

// Mock data for development (to be replaced by real API calls)
export const MOCK_SERVERS: MCPServer[] = [
  {
    id: 'stoa-platform',
    name: 'stoa-platform',
    displayName: 'STOA Platform Tools',
    description: 'Administrative tools for managing the STOA platform: tenants, users, deployments, and configurations.',
    icon: 'settings',
    category: 'platform',
    visibility: {
      roles: ['cpi-admin', 'tenant-admin', 'devops'],
      public: false,
    },
    tools: [
      {
        id: 'tenant-create',
        name: 'tenant-create',
        displayName: 'Create Tenant',
        description: 'Create a new tenant organization',
        enabled: true,
        requires_approval: true,
      },
      {
        id: 'api-deploy',
        name: 'api-deploy',
        displayName: 'Deploy API',
        description: 'Deploy an API to an environment',
        enabled: true,
        requires_approval: false,
      },
      {
        id: 'user-invite',
        name: 'user-invite',
        displayName: 'Invite User',
        description: 'Invite a user to a tenant',
        enabled: true,
        requires_approval: false,
      },
    ],
    status: 'active',
    version: '1.0.0',
    documentation_url: 'https://docs.stoa.cab-i.com/platform-tools',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
  },
  {
    id: 'crm-apis',
    name: 'crm-apis',
    displayName: 'CRM Integration',
    description: 'Customer Relationship Management APIs for customer data, leads, and opportunities.',
    icon: 'users',
    category: 'tenant',
    tenant_id: 'acme-corp',
    visibility: {
      public: true,
    },
    tools: [
      {
        id: 'customer-search',
        name: 'customer-search',
        displayName: 'Search Customers',
        description: 'Search and retrieve customer records',
        enabled: true,
        requires_approval: false,
      },
      {
        id: 'lead-create',
        name: 'lead-create',
        displayName: 'Create Lead',
        description: 'Create a new sales lead',
        enabled: true,
        requires_approval: false,
      },
    ],
    status: 'active',
    version: '2.1.0',
    created_at: '2024-06-01T00:00:00Z',
    updated_at: '2026-01-08T00:00:00Z',
  },
  {
    id: 'billing-services',
    name: 'billing-services',
    displayName: 'Billing & Invoicing',
    description: 'Generate invoices, process payments, and manage billing cycles.',
    icon: 'credit-card',
    category: 'tenant',
    tenant_id: 'acme-corp',
    visibility: {
      public: true,
    },
    tools: [
      {
        id: 'invoice-generate',
        name: 'invoice-generate',
        displayName: 'Generate Invoice',
        description: 'Generate a new invoice for a customer',
        enabled: true,
        requires_approval: false,
      },
      {
        id: 'payment-status',
        name: 'payment-status',
        displayName: 'Check Payment Status',
        description: 'Check the status of a payment',
        enabled: true,
        requires_approval: false,
      },
    ],
    status: 'active',
    version: '1.5.0',
    created_at: '2024-03-15T00:00:00Z',
    updated_at: '2026-01-05T00:00:00Z',
  },
];

export const mcpServersService = {
  getServers,
  getVisibleServers,
  getServer,
  getServersByCategory,
  getMyServerSubscriptions,
  getServerSubscription,
  subscribeToServer,
  updateToolAccess,
  revokeServerSubscription,
  rotateServerKey,
  // Utilities
  canUserSeeServer,
  filterServersByRole,
  // Mock data for development
  MOCK_SERVERS,
};

export default mcpServersService;
