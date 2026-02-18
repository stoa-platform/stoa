/**
 * Tests for MCP Servers Service
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { canUserSeeServer, filterServersByRole, mcpServersService } from './mcpServers';
import type { MCPServer, User } from '../types';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPost = apiClient.post as Mock;
const mockPatch = apiClient.patch as Mock;
const mockDelete = apiClient.delete as Mock;

// Test fixtures
const mockUser: User = {
  id: 'user-1',
  email: 'test@acme.com',
  name: 'Test User',
  roles: ['tenant-admin'],
  permissions: ['apis:read'],
  effective_scopes: ['stoa:catalog:read'],
};

const publicServer: MCPServer = {
  id: 'srv-public',
  name: 'public-tools',
  displayName: 'Public Tools',
  description: 'Public',
  icon: 'globe',
  category: 'public',
  visibility: { public: true },
  tools: [],
  status: 'active',
  version: '1.0.0',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const roleRestrictedServer: MCPServer = {
  ...publicServer,
  id: 'srv-restricted',
  name: 'admin-tools',
  displayName: 'Admin Tools',
  category: 'platform',
  visibility: { public: false, roles: ['cpi-admin'] },
};

const excludedRoleServer: MCPServer = {
  ...publicServer,
  id: 'srv-excluded',
  name: 'special-tools',
  displayName: 'Special Tools',
  visibility: { public: false, roles: ['tenant-admin'], excludeRoles: ['viewer'] },
};

describe('canUserSeeServer', () => {
  it('should return false if user is null', () => {
    expect(canUserSeeServer(publicServer, null)).toBe(false);
  });

  it('should return true for public servers with authenticated user', () => {
    expect(canUserSeeServer(publicServer, mockUser)).toBe(true);
  });

  it('should return false when user lacks required role', () => {
    expect(canUserSeeServer(roleRestrictedServer, mockUser)).toBe(false);
  });

  it('should return true when user has required role', () => {
    const admin = { ...mockUser, roles: ['cpi-admin'] };
    expect(canUserSeeServer(roleRestrictedServer, admin)).toBe(true);
  });

  it('should return false when user has excluded role', () => {
    const viewer = { ...mockUser, roles: ['viewer'] };
    expect(canUserSeeServer(excludedRoleServer, viewer)).toBe(false);
  });

  it('should return true for server with no visibility rules', () => {
    const noRulesServer = { ...publicServer, visibility: { public: false } };
    expect(canUserSeeServer(noRulesServer, mockUser)).toBe(true);
  });

  it('should check exclusion before role matching', () => {
    // User has both an excluded role and a matching role
    const server: MCPServer = {
      ...publicServer,
      visibility: { public: false, roles: ['tenant-admin'], excludeRoles: ['tenant-admin'] },
    };
    expect(canUserSeeServer(server, mockUser)).toBe(false);
  });
});

describe('filterServersByRole', () => {
  it('should return empty array for null user', () => {
    expect(filterServersByRole([publicServer, roleRestrictedServer], null)).toEqual([]);
  });

  it('should filter out servers user cannot see', () => {
    const result = filterServersByRole([publicServer, roleRestrictedServer], mockUser);

    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('srv-public');
  });

  it('should return all servers for admin', () => {
    const admin = { ...mockUser, roles: ['cpi-admin'] };
    const result = filterServersByRole([publicServer, roleRestrictedServer], admin);

    expect(result).toHaveLength(2);
  });
});

describe('mcpServersService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getServers', () => {
    it('should call GET /v1/mcp/servers', async () => {
      mockGet.mockResolvedValueOnce({ data: { servers: [publicServer], total_count: 1 } });

      const result = await mcpServersService.getServers();

      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/servers');
      expect(result).toHaveLength(1);
    });
  });

  describe('getVisibleServers', () => {
    it('should filter servers by user roles', async () => {
      mockGet.mockResolvedValueOnce({
        data: { servers: [publicServer, roleRestrictedServer], total_count: 2 },
      });

      const result = await mcpServersService.getVisibleServers(mockUser);

      expect(result).toHaveLength(1);
      expect(result[0].id).toBe('srv-public');
    });
  });

  describe('getServer', () => {
    it('should call GET /v1/mcp/servers/:id', async () => {
      mockGet.mockResolvedValueOnce({ data: publicServer });

      const result = await mcpServersService.getServer('srv-public');

      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/servers/srv-public');
      expect(result.id).toBe('srv-public');
    });
  });

  describe('getMyServerSubscriptions', () => {
    it('should call GET /v1/mcp/subscriptions', async () => {
      const mockSubs = {
        items: [{ id: 'sub-1' }],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
      mockGet.mockResolvedValueOnce({ data: mockSubs });

      const result = await mcpServersService.getMyServerSubscriptions();

      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/subscriptions');
      expect(result).toEqual([{ id: 'sub-1' }]);
    });
  });

  describe('getServerSubscription', () => {
    it('should call GET /v1/mcp/subscriptions/:id', async () => {
      mockGet.mockResolvedValueOnce({ data: { id: 'sub-1' } });

      const result = await mcpServersService.getServerSubscription('sub-1');

      expect(mockGet).toHaveBeenCalledWith('/v1/mcp/subscriptions/sub-1');
      expect(result.id).toBe('sub-1');
    });
  });

  describe('subscribeToServer', () => {
    it('should call POST /v1/mcp/subscriptions', async () => {
      const request = { server_id: 'srv-1', tool_ids: ['t1'] };
      const mockResponse = { id: 'sub-2', api_key: 'sk-new' };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await mcpServersService.subscribeToServer(request as any);

      expect(mockPost).toHaveBeenCalledWith('/v1/mcp/subscriptions', request);
      expect(result.api_key).toBe('sk-new');
    });
  });

  describe('updateToolAccess', () => {
    it('should call PATCH /v1/mcp/subscriptions/:id/tools', async () => {
      mockPatch.mockResolvedValueOnce({ data: { id: 'sub-1' } });

      await mcpServersService.updateToolAccess('sub-1', ['t1', 't2'], 'enable');

      expect(mockPatch).toHaveBeenCalledWith('/v1/mcp/subscriptions/sub-1/tools', {
        tool_ids: ['t1', 't2'],
        action: 'enable',
      });
    });
  });

  describe('revokeServerSubscription', () => {
    it('should call DELETE /v1/mcp/subscriptions/:id', async () => {
      mockDelete.mockResolvedValueOnce({});

      await mcpServersService.revokeServerSubscription('sub-1');

      expect(mockDelete).toHaveBeenCalledWith('/v1/mcp/subscriptions/sub-1');
    });
  });

  describe('rotateServerKey', () => {
    it('should call POST /v1/mcp/subscriptions/:id/rotate-key with default grace', async () => {
      mockPost.mockResolvedValueOnce({
        data: {
          new_api_key: 'sk-rotated',
          new_api_key_prefix: 'sk-rot',
          old_key_expires_at: '2026-02-08T12:00:00Z',
          grace_period_hours: 24,
          rotation_count: 1,
        },
      });

      const result = await mcpServersService.rotateServerKey('sub-1');

      expect(mockPost).toHaveBeenCalledWith('/v1/mcp/subscriptions/sub-1/rotate-key', {
        grace_period_hours: 24,
      });
      expect(result.new_api_key).toBe('sk-rotated');
    });

    it('should accept custom grace period', async () => {
      mockPost.mockResolvedValueOnce({
        data: { new_api_key: 'sk-r', old_key_expires_at: '2026-02-09T12:00:00Z' },
      });

      await mcpServersService.rotateServerKey('sub-1', 48);

      expect(mockPost).toHaveBeenCalledWith('/v1/mcp/subscriptions/sub-1/rotate-key', {
        grace_period_hours: 48,
      });
    });
  });

  describe('getServersByCategory', () => {
    it('should group servers by category', async () => {
      const platformServer = { ...publicServer, id: 'srv-p', category: 'platform' as const };
      const tenantServer = { ...publicServer, id: 'srv-t', category: 'tenant' as const };

      mockGet.mockResolvedValueOnce({
        data: { servers: [publicServer, platformServer, tenantServer], total_count: 3 },
      });

      const result = await mcpServersService.getServersByCategory(mockUser);

      // Only public server passes filtering for tenant-admin
      expect(result.public).toHaveLength(1);
    });
  });
});
