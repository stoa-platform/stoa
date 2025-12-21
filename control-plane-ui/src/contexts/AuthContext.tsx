import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useAuth as useOidcAuth, hasAuthParams } from 'react-oidc-context';
import type { User } from '../types';
import { apiService } from '../services/api';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
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
  ],
  'tenant-admin': [
    'apis:create', 'apis:read', 'apis:update', 'apis:delete', 'apis:deploy',
    'apps:create', 'apps:read', 'apps:update', 'apps:delete',
    'users:create', 'users:read', 'users:update',
    'audit:read',
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
  const roles = profile.roles || profile.realm_access?.roles || [];

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

  useEffect(() => {
    if (oidc.user) {
      setUser(extractUserFromToken(oidc.user));
      // Set the access token for API calls
      if (oidc.user.access_token) {
        apiService.setAuthToken(oidc.user.access_token);
      }
    } else {
      setUser(null);
      apiService.clearAuthToken();
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
