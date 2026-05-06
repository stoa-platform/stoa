import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useMemo,
  useRef,
  ReactNode,
} from 'react';
import { useAuth as useOidcAuth, hasAuthParams } from 'react-oidc-context';
import { useQueryClient } from '@tanstack/react-query';
import type { User } from '../types';
import { apiService } from '../services/api';
import { markRedirecting, resetRedirecting } from '../services/http/redirect';
import { decodeJwtPayload, isMcpCallbackPath } from './auth-helpers';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isReady: boolean; // Token is set and ready for API calls
  /**
   * Raw Keycloak JWT exposed on the context by design — consumers MUST be
   * in the allowlist below. Adding new consumers requires a security review
   * (track token leak surface).
   *
   * Known consumers (2026-05-06):
   * - none
   *
   * Grafana expert mode MUST use backend/proxy/session authorization rather
   * than URL token injection.
   */
  accessToken: string | null;
  login: () => void;
  logout: () => void;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: string) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Role to permissions mapping (mirrors backend)
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
    'consumers:create',
    'consumers:read',
    'consumers:write',
    'consumers:delete',
    'users:create',
    'users:read',
    'users:update',
    'users:delete',
    'audit:read',
    'admin:servers',
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
    'consumers:create',
    'consumers:read',
    'consumers:write',
    'consumers:delete',
    'users:create',
    'users:read',
    'users:update',
    'audit:read',
    'admin:servers',
  ],
  devops: [
    'apis:create',
    'apis:read',
    'apis:update',
    'apis:deploy',
    'apps:read',
    'consumers:read',
    'audit:read',
  ],
  viewer: ['apis:read', 'apps:read', 'consumers:read', 'audit:read'],
};

function extractUserFromToken(oidcUser: any): User | null {
  if (!oidcUser?.profile) return null;

  const profile = oidcUser.profile;

  // Roles are in the access_token, not in the id_token (profile)
  // Decode the access_token to get realm_access.roles
  let roles: string[] = [];
  if (oidcUser.access_token) {
    try {
      const payload = decodeJwtPayload(oidcUser.access_token) as {
        realm_access?: { roles?: string[] };
      };
      roles = payload.realm_access?.roles || [];
    } catch (e) {
      // P2-9: silence residual diagnostic in prod to avoid leaking parser
      // state to browser consoles of end users.
      if (import.meta.env.DEV) console.warn('Failed to decode access_token for roles', e);
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
    rolePerms.forEach((p) => permissions.add(p));
  }

  return {
    id: profile.sub,
    email: profile.email || '',
    name: profile.name || profile.preferred_username || '',
    username: profile.preferred_username || '',
    roles,
    tenant_id: profile.tenant_id,
    permissions: Array.from(permissions),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const oidc = useOidcAuth();
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [isReady, setIsReady] = useState(false);
  const prevTokenRef = useRef<string | null>(null);
  // P1-6: guard setState after unmount (HMR, logout+remount, etc.).
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (oidc.user) {
      const token = oidc.user.access_token;
      // Skip re-extraction if token hasn't changed (StrictMode + silent renew)
      if (token && token !== prevTokenRef.current) {
        prevTokenRef.current = token;
        const tokenUser = extractUserFromToken(oidc.user);
        setUser(tokenUser);
        apiService.setAuthToken(token);
        setIsReady(true);
        // Prefetch tenants immediately — most pages need this data
        queryClient.prefetchQuery({
          queryKey: ['tenants'],
          queryFn: () => apiService.getTenants(),
          staleTime: 5 * 60 * 1000, // 5 minutes
        });
        // CAB-1634: Enrich user with role display names from /v1/me
        apiService
          .getMe()
          .then((me) => {
            if (!mountedRef.current) return; // P1-6
            if (me.role_display_names) {
              setUser((prev) =>
                prev ? { ...prev, role_display_names: me.role_display_names } : prev
              );
            }
          })
          .catch(() => {
            // Non-critical: display names are cosmetic, raw roles still work
          });
      } else if (!token) {
        setUser(extractUserFromToken(oidc.user));
      }
    } else {
      prevTokenRef.current = null;
      setUser(null);
      apiService.clearAuthToken();
      setIsReady(false);
    }
  }, [oidc.user, queryClient]);

  // CAB-1122: Register token refresher for 401 auto-retry.
  // P1-7: depend on the two stable function refs, not the whole `oidc`
  // object (react-oidc-context returns a new object on most renders).
  // P1-16: mark the redirect in flight so applyFriendlyErrorMessage does
  // not flash a tech error between `signinRedirect()` and the actual
  // browser navigation; reset the flag if the redirect itself throws so
  // we never stay in "silence forever" mode.
  const { signinSilent, signinRedirect } = oidc;
  useEffect(() => {
    apiService.setTokenRefresher(async () => {
      const redirectToLogin = async () => {
        markRedirecting();
        try {
          await signinRedirect();
        } catch (err) {
          resetRedirecting();
          throw err;
        }
      };
      try {
        const renewed = await signinSilent();
        if (renewed?.access_token) {
          return renewed.access_token;
        }
        // Silent renew succeeded but no token — session expired
        await redirectToLogin();
        return null;
      } catch {
        await redirectToLogin();
        return null;
      }
    });
  }, [signinSilent, signinRedirect]);

  // Auto-login if we have auth params in URL (callback from Keycloak).
  // Skip on /mcp-connectors/callback — those code/state params are from
  // the MCP provider (e.g. Linear), not Keycloak. Without this check,
  // oidc-client-ts misinterprets the MCP OAuth callback as a Keycloak
  // callback and redirects to login (P1-15: basePath-robust).
  useEffect(() => {
    if (
      !oidc.isAuthenticated &&
      !oidc.isLoading &&
      hasAuthParams() &&
      !isMcpCallbackPath(window.location.pathname)
    ) {
      oidc.signinRedirect();
    }
  }, [oidc.isAuthenticated, oidc.isLoading, oidc]);

  const hasPermission = useCallback(
    (permission: string): boolean => {
      return user?.permissions.includes(permission) ?? false;
    },
    [user]
  );

  const hasRole = useCallback(
    (role: string): boolean => {
      return user?.roles.includes(role) ?? false;
    },
    [user]
  );

  const login = useCallback(() => oidc.signinRedirect(), [oidc]);
  const logout = useCallback(() => oidc.signoutRedirect(), [oidc]);

  const accessToken = oidc.user?.access_token ?? null;

  const value: AuthContextType = useMemo(
    () => ({
      user,
      isAuthenticated: oidc.isAuthenticated,
      isLoading: oidc.isLoading,
      isReady,
      accessToken,
      login,
      logout,
      hasPermission,
      hasRole,
    }),
    [
      user,
      oidc.isAuthenticated,
      oidc.isLoading,
      isReady,
      accessToken,
      login,
      logout,
      hasPermission,
      hasRole,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
