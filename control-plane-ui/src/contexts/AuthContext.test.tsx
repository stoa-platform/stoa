import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock react-oidc-context
const mockSigninRedirect = vi.fn();
const mockSignoutRedirect = vi.fn();
let mockOidcState = {
  isAuthenticated: false,
  isLoading: false,
  user: null as any,
  signinRedirect: mockSigninRedirect,
  signoutRedirect: mockSignoutRedirect,
  signinSilent: vi.fn().mockResolvedValue(null),
};

vi.mock('react-oidc-context', () => ({
  useAuth: () => mockOidcState,
  hasAuthParams: () => false,
}));

vi.mock('../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    setTokenRefresher: vi.fn(),
    getTenants: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../services/mcpGatewayApi', () => ({
  mcpGatewayService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

import { AuthProvider, useAuth } from './AuthContext';
import { apiService } from '../services/api';
import { mcpGatewayService } from '../services/mcpGatewayApi';

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

// Helper: create a fake OIDC user with JWT access_token containing roles
function createOidcUser(roles: string[], name = 'Parzival', email = 'parzival@oasis.gg') {
  const payload = { realm_access: { roles }, sub: 'user-1' };
  const fakeJwt = `header.${btoa(JSON.stringify(payload))}.signature`;
  return {
    access_token: fakeJwt,
    profile: { sub: 'user-1', email, name, preferred_username: name.toLowerCase() },
  };
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockOidcState = {
      isAuthenticated: false,
      isLoading: false,
      user: null,
      signinRedirect: mockSigninRedirect,
      signoutRedirect: mockSignoutRedirect,
    };
  });

  it('throws error when useAuth is used outside AuthProvider', () => {
    expect(() => {
      renderHook(() => useAuth());
    }).toThrow('useAuth must be used within an AuthProvider');
  });

  it('returns unauthenticated state when no OIDC user', () => {
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.isReady).toBe(false);
  });

  it('returns loading state when OIDC is loading', () => {
    mockOidcState.isLoading = true;
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    expect(result.current.isLoading).toBe(true);
  });

  it('extracts user from OIDC token with cpi-admin role', () => {
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = createOidcUser(['cpi-admin']);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    expect(result.current.user).not.toBeNull();
    expect(result.current.user?.name).toBe('Parzival');
    expect(result.current.user?.email).toBe('parzival@oasis.gg');
    expect(result.current.user?.roles).toContain('cpi-admin');
    expect(result.current.isReady).toBe(true);
  });

  it('sets auth token on API services when authenticated', () => {
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = createOidcUser(['cpi-admin']);

    renderHook(() => useAuth(), { wrapper: createWrapper() });

    expect(apiService.setAuthToken).toHaveBeenCalled();
    expect(mcpGatewayService.setAuthToken).toHaveBeenCalled();
  });

  it('clears auth token when user is null', () => {
    mockOidcState.isAuthenticated = false;
    mockOidcState.user = null;

    renderHook(() => useAuth(), { wrapper: createWrapper() });

    expect(apiService.clearAuthToken).toHaveBeenCalled();
    expect(mcpGatewayService.clearAuthToken).toHaveBeenCalled();
  });

  it('hasPermission returns true for cpi-admin with tenants:create', () => {
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = createOidcUser(['cpi-admin']);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    expect(result.current.hasPermission('tenants:create')).toBe(true);
    expect(result.current.hasPermission('tenants:delete')).toBe(true);
  });

  it('hasPermission returns false for viewer with write permissions', () => {
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = createOidcUser(['viewer']);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    expect(result.current.hasPermission('apis:read')).toBe(true);
    expect(result.current.hasPermission('apis:create')).toBe(false);
    expect(result.current.hasPermission('tenants:delete')).toBe(false);
  });

  it('grants consumers permissions based on role (CAB-864)', () => {
    // cpi-admin gets full consumers CRUD
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = createOidcUser(['cpi-admin']);
    const { result: admin } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    expect(admin.current.hasPermission('consumers:read')).toBe(true);
    expect(admin.current.hasPermission('consumers:write')).toBe(true);
    expect(admin.current.hasPermission('consumers:create')).toBe(true);
    expect(admin.current.hasPermission('consumers:delete')).toBe(true);

    // viewer gets read-only consumers access
    mockOidcState.user = createOidcUser(['viewer']);
    const { result: viewer } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    expect(viewer.current.hasPermission('consumers:read')).toBe(true);
    expect(viewer.current.hasPermission('consumers:write')).toBe(false);

    // devops gets read-only consumers access
    mockOidcState.user = createOidcUser(['devops']);
    const { result: devops } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    expect(devops.current.hasPermission('consumers:read')).toBe(true);
    expect(devops.current.hasPermission('consumers:write')).toBe(false);
    expect(devops.current.hasPermission('consumers:delete')).toBe(false);
  });

  it('hasRole returns correct values', () => {
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = createOidcUser(['tenant-admin']);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    expect(result.current.hasRole('tenant-admin')).toBe(true);
    expect(result.current.hasRole('cpi-admin')).toBe(false);
  });

  it('login triggers OIDC signin redirect', () => {
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    act(() => result.current.login());
    expect(mockSigninRedirect).toHaveBeenCalled();
  });

  it('logout triggers OIDC signout redirect', () => {
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    act(() => result.current.logout());
    expect(mockSignoutRedirect).toHaveBeenCalled();
  });

  it('prefetches tenants when authenticated', () => {
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = createOidcUser(['cpi-admin']);

    renderHook(() => useAuth(), { wrapper: createWrapper() });

    // getTenants is called via prefetchQuery
    expect(apiService.getTenants).toHaveBeenCalled();
  });
});
