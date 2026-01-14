import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useAuth as useOidcAuth, hasAuthParams } from 'react-oidc-context';
import type { User } from '../types';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  accessToken: string | null;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function extractUserFromToken(oidcUser: any): User | null {
  if (!oidcUser?.profile) return null;

  const profile = oidcUser.profile;

  // Extract tenant_id and organization from token if available
  let tenantId: string | undefined;
  let organization: string | undefined;

  if (oidcUser.access_token) {
    try {
      const payload = JSON.parse(atob(oidcUser.access_token.split('.')[1]));
      tenantId = payload.tenant_id;
      organization = payload.organization;
    } catch (e) {
      console.warn('Failed to decode access_token', e);
    }
  }

  return {
    id: profile.sub,
    email: profile.email || '',
    name: profile.name || profile.preferred_username || '',
    tenant_id: tenantId || profile.tenant_id,
    organization: organization || profile.organization,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const oidc = useOidcAuth();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (oidc.user) {
      setUser(extractUserFromToken(oidc.user));
    } else {
      setUser(null);
    }
  }, [oidc.user]);

  // Auto-login if we have auth params in URL (callback from Keycloak)
  useEffect(() => {
    if (!oidc.isAuthenticated && !oidc.isLoading && hasAuthParams()) {
      oidc.signinRedirect();
    }
  }, [oidc.isAuthenticated, oidc.isLoading]);

  const value: AuthContextType = {
    user,
    isAuthenticated: oidc.isAuthenticated,
    isLoading: oidc.isLoading,
    accessToken: oidc.user?.access_token || null,
    login: () => oidc.signinRedirect(),
    logout: () => oidc.signoutRedirect(),
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
