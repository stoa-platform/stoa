/**
 * STOA Developer Portal - Authentication Context with RBAC
 *
 * Provides authentication state and RBAC helpers (hasPermission, hasRole, hasScope).
 * Fetches permissions from /v1/me endpoint (single source of truth).
 */
import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react';
import { useAuth as useOidcAuth, hasAuthParams } from 'react-oidc-context';
import type { User, UserPermissionsResponse } from '../types';
import { apiClient, setAccessToken } from '../services/api';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isReady: boolean; // True when permissions are loaded
  accessToken: string | null;

  // RBAC helpers
  hasPermission: (permission: string) => boolean;
  hasAnyPermission: (permissions: string[]) => boolean;
  hasAllPermissions: (permissions: string[]) => boolean;
  hasRole: (role: string) => boolean;
  hasScope: (scope: string) => boolean;

  // Actions
  login: () => void;
  logout: () => void;
  refreshPermissions: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Role to permissions mapping (fallback if /v1/me fails)
const ROLE_PERMISSIONS: Record<string, string[]> = {
  'cpi-admin': [
    'tenants:create', 'tenants:read', 'tenants:update', 'tenants:delete',
    'apis:create', 'apis:read', 'apis:update', 'apis:delete', 'apis:deploy', 'apis:promote',
    'apps:create', 'apps:read', 'apps:update', 'apps:delete',
    'users:manage', 'audit:read',
  ],
  'tenant-admin': [
    'tenants:read',
    'apis:create', 'apis:read', 'apis:update', 'apis:delete', 'apis:deploy', 'apis:promote',
    'apps:create', 'apps:read', 'apps:update', 'apps:delete',
    'users:manage', 'audit:read',
  ],
  'devops': [
    'tenants:read',
    'apis:create', 'apis:read', 'apis:update', 'apis:deploy', 'apis:promote',
    'apps:create', 'apps:read', 'apps:update',
    'audit:read',
  ],
  'viewer': [
    'tenants:read', 'apis:read', 'apps:read', 'audit:read',
  ],
};

// Role to scopes mapping (fallback if /v1/me fails)
const ROLE_SCOPES: Record<string, string[]> = {
  'cpi-admin': [
    'stoa:platform:read', 'stoa:platform:write',
    'stoa:catalog:read', 'stoa:catalog:write',
    'stoa:subscriptions:read', 'stoa:subscriptions:write',
    'stoa:metrics:read', 'stoa:logs:full',
    'stoa:security:read', 'stoa:security:write',
    'stoa:tools:read', 'stoa:tools:execute',
  ],
  'tenant-admin': [
    'stoa:catalog:read', 'stoa:catalog:write',
    'stoa:subscriptions:read', 'stoa:subscriptions:write',
    'stoa:metrics:read', 'stoa:logs:functional',
    'stoa:tools:read', 'stoa:tools:execute',
  ],
  'devops': [
    'stoa:catalog:read', 'stoa:catalog:write',
    'stoa:subscriptions:read',
    'stoa:metrics:read', 'stoa:logs:technical',
    'stoa:tools:read', 'stoa:tools:execute',
  ],
  'viewer': [
    'stoa:catalog:read', 'stoa:subscriptions:read', 'stoa:metrics:read', 'stoa:tools:read',
  ],
};

function derivePermissionsFromRoles(roles: string[]): string[] {
  const perms = new Set<string>();
  roles.forEach(role => {
    ROLE_PERMISSIONS[role]?.forEach(p => perms.add(p));
  });
  return Array.from(perms).sort();
}

function deriveScopesFromRoles(roles: string[]): string[] {
  const scopes = new Set<string>();
  roles.forEach(role => {
    ROLE_SCOPES[role]?.forEach(s => scopes.add(s));
  });
  return Array.from(scopes).sort();
}

function filterSystemRoles(roles: string[]): string[] {
  return roles.filter(r =>
    !r.startsWith('default-roles-') &&
    r !== 'offline_access' &&
    r !== 'uma_authorization'
  );
}

function extractUserFromToken(oidcUser: any): Partial<User> | null {
  if (!oidcUser?.profile) return null;

  const profile = oidcUser.profile;

  // Extract tenant_id and organization from token if available
  let tenantId: string | undefined;
  let organization: string | undefined;
  let roles: string[] = [];

  if (oidcUser.access_token) {
    try {
      const payload = JSON.parse(atob(oidcUser.access_token.split('.')[1]));
      // Try multiple possible claim locations for tenant_id
      tenantId = payload.tenant_id
        || payload.tenantId
        || payload['tenant-id']
        || payload.resource_access?.['control-plane-api']?.tenant_id;
      organization = payload.organization || payload.org;

      // Extract roles from realm_access
      roles = filterSystemRoles(payload.realm_access?.roles || []);
    } catch (e) {
      console.warn('[AuthContext] Failed to decode access_token', e);
    }
  }

  const isCpiAdmin = roles.includes('cpi-admin');

  return {
    id: profile.sub,
    email: profile.email || '',
    name: profile.name || profile.preferred_username || '',
    tenant_id: tenantId || profile.tenant_id,
    organization: organization || profile.organization,
    roles,
    permissions: [], // Will be populated from /v1/me or fallback
    effective_scopes: [], // Will be populated from /v1/me or fallback
    is_admin: isCpiAdmin,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const oidc = useOidcAuth();
  const [user, setUser] = useState<User | null>(null);
  const [isReady, setIsReady] = useState(false);

  // Fetch permissions from backend (single source of truth)
  const fetchUserPermissions = useCallback(async (): Promise<void> => {
    if (!oidc.user?.access_token) {
      console.warn('[AuthContext] No access token available for /v1/me');
      return;
    }

    try {
      const response = await apiClient.get<UserPermissionsResponse>('/v1/me');
      const data = response.data;

      setUser(prev => prev ? {
        ...prev,
        roles: data.roles,
        permissions: data.permissions,
        effective_scopes: data.effective_scopes,
        tenant_id: data.tenant_id || prev.tenant_id,
      } : null);

      console.log('[AuthContext] Permissions loaded from /v1/me', {
        roles: data.roles,
        permissionsCount: data.permissions.length,
        scopesCount: data.effective_scopes.length,
      });
    } catch (error) {
      console.warn('[AuthContext] Failed to fetch /v1/me, using fallback', error);
      // Fallback: derive permissions from roles locally
      setUser(prev => {
        if (!prev) return null;
        return {
          ...prev,
          permissions: derivePermissionsFromRoles(prev.roles),
          effective_scopes: deriveScopesFromRoles(prev.roles),
        };
      });
    } finally {
      setIsReady(true);
    }
  }, [oidc.user?.access_token]);

  // Handle OIDC user changes
  useEffect(() => {
    if (oidc.user) {
      const extractedUser = extractUserFromToken(oidc.user);
      if (extractedUser) {
        // Set initial user with roles from token
        const initialUser: User = {
          id: extractedUser.id!,
          email: extractedUser.email!,
          name: extractedUser.name!,
          tenant_id: extractedUser.tenant_id,
          organization: extractedUser.organization,
          roles: extractedUser.roles || [],
          permissions: derivePermissionsFromRoles(extractedUser.roles || []),
          effective_scopes: deriveScopesFromRoles(extractedUser.roles || []),
          is_admin: extractedUser.is_admin,
        };
        setUser(initialUser);
        setAccessToken(oidc.user.access_token || null);

        // Fetch full permissions from backend
        fetchUserPermissions();
      }
    } else {
      setUser(null);
      setAccessToken(null);
      setIsReady(false);
    }
  }, [oidc.user, fetchUserPermissions]);

  // Auto-login if we have auth params in URL (callback from Keycloak)
  useEffect(() => {
    if (!oidc.isAuthenticated && !oidc.isLoading && hasAuthParams()) {
      oidc.signinRedirect();
    }
  }, [oidc.isAuthenticated, oidc.isLoading]);

  // RBAC Helpers
  const hasPermission = useCallback((permission: string): boolean => {
    if (!user) return false;
    return user.permissions.includes(permission);
  }, [user]);

  const hasAnyPermission = useCallback((permissions: string[]): boolean => {
    if (!user) return false;
    return permissions.some(p => user.permissions.includes(p));
  }, [user]);

  const hasAllPermissions = useCallback((permissions: string[]): boolean => {
    if (!user) return false;
    return permissions.every(p => user.permissions.includes(p));
  }, [user]);

  const hasRole = useCallback((role: string): boolean => {
    if (!user) return false;
    return user.roles.includes(role);
  }, [user]);

  const hasScope = useCallback((scope: string): boolean => {
    if (!user) return false;
    return user.effective_scopes.includes(scope);
  }, [user]);

  const value: AuthContextType = {
    user,
    isAuthenticated: oidc.isAuthenticated,
    isLoading: oidc.isLoading,
    isReady,
    accessToken: oidc.user?.access_token || null,

    // RBAC helpers
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    hasRole,
    hasScope,

    // Actions
    login: () => oidc.signinRedirect(),
    logout: () => oidc.signoutRedirect(),
    refreshPermissions: fetchUserPermissions,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

// Convenience hooks for specific checks
export function usePermission(permission: string): boolean {
  const { hasPermission } = useAuth();
  return hasPermission(permission);
}

export function useRole(role: string): boolean {
  const { hasRole } = useAuth();
  return hasRole(role);
}

export function useScope(scope: string): boolean {
  const { hasScope } = useAuth();
  return hasScope(scope);
}
