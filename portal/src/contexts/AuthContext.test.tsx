/**
 * Tests for AuthContext — RBAC provider
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
import { AuthProvider, useAuth, usePermission, useRole, useScope } from './AuthContext';

// Mock react-oidc-context
let mockOidcState: {
  user: any;
  isAuthenticated: boolean;
  isLoading: boolean;
};

vi.mock('react-oidc-context', () => ({
  useAuth: () => mockOidcState,
  hasAuthParams: () => false,
}));

// Mock api module
const mockApiGet = vi.fn();
vi.mock('../services/api', () => ({
  apiClient: {
    get: (...args: any[]) => mockApiGet(...args),
  },
  setAccessToken: vi.fn(),
}));

// Helper: create a JWT-like token with given payload
function fakeToken(payload: object): string {
  const header = btoa(JSON.stringify({ alg: 'RS256' }));
  const body = btoa(JSON.stringify(payload));
  return `${header}.${body}.signature`;
}

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockOidcState = {
      user: null,
      isAuthenticated: false,
      isLoading: false,
    };
  });

  describe('unauthenticated state', () => {
    it('should return null user when not authenticated', () => {
      const { result } = renderHook(() => useAuth(), { wrapper });

      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
    });

    it('should return false for all permission checks', () => {
      const { result } = renderHook(() => useAuth(), { wrapper });

      expect(result.current.hasPermission('apis:read')).toBe(false);
      expect(result.current.hasAnyPermission(['apis:read'])).toBe(false);
      expect(result.current.hasAllPermissions(['apis:read'])).toBe(false);
      expect(result.current.hasRole('cpi-admin')).toBe(false);
      expect(result.current.hasScope('stoa:catalog:read')).toBe(false);
    });
  });

  describe('authenticated state', () => {
    beforeEach(() => {
      const tokenPayload = {
        sub: 'user-1',
        realm_access: { roles: ['tenant-admin', 'default-roles-stoa', 'offline_access'] },
        tenant_id: 'acme',
        organization: 'Acme Corp',
      };

      mockOidcState = {
        user: {
          access_token: fakeToken(tokenPayload),
          profile: {
            sub: 'user-1',
            email: 'test@acme.com',
            name: 'Test User',
          },
        },
        isAuthenticated: true,
        isLoading: false,
      };
    });

    it('should extract user from token and filter system roles', async () => {
      // /v1/me will fail, triggering fallback
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.user).not.toBeNull();
      });

      expect(result.current.user!.id).toBe('user-1');
      expect(result.current.user!.email).toBe('test@acme.com');
      expect(result.current.user!.roles).toContain('tenant-admin');
      // System roles should be filtered
      expect(result.current.user!.roles).not.toContain('default-roles-stoa');
      expect(result.current.user!.roles).not.toContain('offline_access');
    });

    it('should derive permissions from roles as fallback', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isReady).toBe(true);
      });

      // tenant-admin should have these permissions
      expect(result.current.hasPermission('apis:read')).toBe(true);
      expect(result.current.hasPermission('apis:create')).toBe(true);
      expect(result.current.hasPermission('tenants:read')).toBe(true);
      // tenant-admin should NOT have tenants:create
      expect(result.current.hasPermission('tenants:create')).toBe(false);
    });

    it('should derive scopes from roles as fallback', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isReady).toBe(true);
      });

      expect(result.current.hasScope('stoa:catalog:read')).toBe(true);
      expect(result.current.hasScope('stoa:catalog:write')).toBe(true);
      // tenant-admin should NOT have platform scopes
      expect(result.current.hasScope('stoa:platform:read')).toBe(false);
    });

    it('should use /v1/me response when available', async () => {
      mockApiGet.mockResolvedValueOnce({
        data: {
          roles: ['tenant-admin'],
          permissions: ['custom:permission'],
          effective_scopes: ['custom:scope'],
          tenant_id: 'custom-tenant',
        },
      });

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isReady).toBe(true);
      });

      expect(result.current.hasPermission('custom:permission')).toBe(true);
      expect(result.current.hasScope('custom:scope')).toBe(true);
    });

    it('should extract tenant_id from token', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.user).not.toBeNull();
      });

      expect(result.current.user!.tenant_id).toBe('acme');
      expect(result.current.user!.organization).toBe('Acme Corp');
    });
  });

  describe('RBAC helpers', () => {
    beforeEach(() => {
      const tokenPayload = {
        sub: 'user-1',
        realm_access: { roles: ['devops'] },
      };

      mockOidcState = {
        user: {
          access_token: fakeToken(tokenPayload),
          profile: { sub: 'user-1', email: 'dev@acme.com', name: 'Dev' },
        },
        isAuthenticated: true,
        isLoading: false,
      };
    });

    it('hasAnyPermission should return true if any permission matches', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isReady).toBe(true);
      });

      expect(result.current.hasAnyPermission(['tenants:create', 'apis:read'])).toBe(true);
      expect(result.current.hasAnyPermission(['tenants:create', 'tenants:delete'])).toBe(false);
    });

    it('hasAllPermissions should require all permissions', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isReady).toBe(true);
      });

      expect(result.current.hasAllPermissions(['apis:read', 'apis:create'])).toBe(true);
      expect(result.current.hasAllPermissions(['apis:read', 'tenants:create'])).toBe(false);
    });

    it('hasRole should check role existence', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.user).not.toBeNull();
      });

      expect(result.current.hasRole('devops')).toBe(true);
      expect(result.current.hasRole('cpi-admin')).toBe(false);
    });
  });

  describe('convenience hooks', () => {
    it('useAuth should throw when used outside AuthProvider', () => {
      expect(() => {
        renderHook(() => useAuth());
      }).toThrow('useAuth must be used within an AuthProvider');
    });

    it('usePermission should return boolean', async () => {
      const tokenPayload = {
        sub: 'user-1',
        realm_access: { roles: ['viewer'] },
      };
      mockOidcState = {
        user: {
          access_token: fakeToken(tokenPayload),
          profile: { sub: 'user-1', email: 'v@acme.com', name: 'Viewer' },
        },
        isAuthenticated: true,
        isLoading: false,
      };
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => usePermission('apis:read'), { wrapper });

      await waitFor(() => {
        expect(result.current).toBe(true);
      });
    });

    it('useRole should return boolean', async () => {
      const tokenPayload = {
        sub: 'user-1',
        realm_access: { roles: ['viewer'] },
      };
      mockOidcState = {
        user: {
          access_token: fakeToken(tokenPayload),
          profile: { sub: 'user-1', email: 'v@acme.com', name: 'Viewer' },
        },
        isAuthenticated: true,
        isLoading: false,
      };
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useRole('viewer'), { wrapper });

      await waitFor(() => {
        expect(result.current).toBe(true);
      });
    });

    it('useScope should return boolean', async () => {
      const tokenPayload = {
        sub: 'user-1',
        realm_access: { roles: ['viewer'] },
      };
      mockOidcState = {
        user: {
          access_token: fakeToken(tokenPayload),
          profile: { sub: 'user-1', email: 'v@acme.com', name: 'Viewer' },
        },
        isAuthenticated: true,
        isLoading: false,
      };
      mockApiGet.mockRejectedValueOnce(new Error('Not available'));

      const { result } = renderHook(() => useScope('stoa:catalog:read'), { wrapper });

      await waitFor(() => {
        expect(result.current).toBe(true);
      });
    });
  });
});
