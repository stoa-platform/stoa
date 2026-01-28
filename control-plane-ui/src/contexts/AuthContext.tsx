// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useAuth as useOidcAuth, hasAuthParams } from 'react-oidc-context';
import type { User } from '../types';
import { apiService } from '../services/api';
import { mcpGatewayService } from '../services/mcpGatewayApi';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isReady: boolean; // Token is set and ready for API calls
  login: () => void;
  logout: () => void;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Role to permissions mapping (mirrors backend)
const ROLE_PERMISSIONS: Record<string, string[]> = {
  'cpi-admin': [
    'tenants:create', 'tenants:read', 'tenants:update', 'tenants:delete',
    'apis:create', 'apis:read', 'apis:update', 'apis:delete', 'apis:deploy',
    'apps:create', 'apps:read', 'apps:update', 'apps:delete',
    'users:create', 'users:read', 'users:update', 'users:delete',
    'audit:read',
    'admin:servers',
  ],
  'tenant-admin': [
    'apis:create', 'apis:read', 'apis:update', 'apis:delete', 'apis:deploy',
    'apps:create', 'apps:read', 'apps:update', 'apps:delete',
    'users:create', 'users:read', 'users:update',
    'audit:read',
    'admin:servers',
  ],
  'devops': [
    'apis:create', 'apis:read', 'apis:update', 'apis:deploy',
    'apps:read',
    'audit:read',
  ],
  'viewer': [
    'apis:read',
    'apps:read',
    'audit:read',
  ],
};

function extractUserFromToken(oidcUser: any): User | null {
  if (!oidcUser?.profile) return null;

  const profile = oidcUser.profile;

  // Roles are in the access_token, not in the id_token (profile)
  // Decode the access_token to get realm_access.roles
  let roles: string[] = [];
  if (oidcUser.access_token) {
    try {
      const payload = JSON.parse(atob(oidcUser.access_token.split('.')[1]));
      roles = payload.realm_access?.roles || [];
    } catch (e) {
      console.warn('Failed to decode access_token for roles', e);
    }
  }

  // Fallback to profile if available
  if (roles.length === 0) {
    roles = profile.roles || profile.realm_access?.roles || [];
  }

  // Calculate permissions from roles
  const permissions = new Set<string>();
  for (const role of roles) {
    const rolePerms = ROLE_PERMISSIONS[role] || [];
    rolePerms.forEach(p => permissions.add(p));
  }

  return {
    id: profile.sub,
    email: profile.email || '',
    name: profile.name || profile.preferred_username || '',
    roles,
    tenant_id: profile.tenant_id,
    permissions: Array.from(permissions),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const oidc = useOidcAuth();
  const [user, setUser] = useState<User | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    console.log('[AuthContext] useEffect triggered, oidc.user:', !!oidc.user);
    if (oidc.user) {
      setUser(extractUserFromToken(oidc.user));
      // Set the access token for API calls
      if (oidc.user.access_token) {
        console.log('[AuthContext] Setting auth token');
        apiService.setAuthToken(oidc.user.access_token);
        mcpGatewayService.setAuthToken(oidc.user.access_token);
        setIsReady(true); // Token is now set
      } else {
        console.warn('[AuthContext] oidc.user exists but no access_token');
      }
    } else {
      setUser(null);
      apiService.clearAuthToken();
      mcpGatewayService.clearAuthToken();
      setIsReady(false);
    }
  }, [oidc.user]);

  // Auto-login if we have auth params in URL (callback from Keycloak)
  useEffect(() => {
    if (!oidc.isAuthenticated && !oidc.isLoading && hasAuthParams()) {
      oidc.signinRedirect();
    }
  }, [oidc.isAuthenticated, oidc.isLoading]);

  const hasPermission = (permission: string): boolean => {
    return user?.permissions.includes(permission) ?? false;
  };

  const hasRole = (role: string): boolean => {
    return user?.roles.includes(role) ?? false;
  };

  const value: AuthContextType = {
    user,
    isAuthenticated: oidc.isAuthenticated,
    isLoading: oidc.isLoading,
    isReady, // Token is set and ready for API calls
    login: () => oidc.signinRedirect(),
    logout: () => oidc.signoutRedirect(),
    hasPermission,
    hasRole,
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
