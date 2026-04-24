import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ─── Hoisted mocks — referenced by vi.mock factories ───────────────────────
const { mockOidcState, setTokenRefresher, getMeState } = vi.hoisted(() => {
  const state = {
    isAuthenticated: false,
    isLoading: false,
    user: null as unknown,
    signinSilent: vi.fn(),
    signinRedirect: vi.fn(),
    signoutRedirect: vi.fn(),
  };
  return {
    mockOidcState: state,
    setTokenRefresher: vi.fn(),
    getMeState: {
      resolver: null as
        | ((v: { role_display_names?: Record<string, string> }) => void)
        | null,
    },
  };
});

vi.mock('react-oidc-context', () => ({
  useAuth: () => mockOidcState,
  hasAuthParams: () => false,
}));

vi.mock('../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    setTokenRefresher,
    getTenants: vi.fn().mockResolvedValue([]),
    getMe: vi.fn(
      () =>
        new Promise((resolve) => {
          getMeState.resolver = resolve as typeof getMeState.resolver;
        }),
    ),
  },
}));

import { AuthProvider, useAuth } from './AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

function craftOidcUser() {
  const payload = { realm_access: { roles: ['viewer'] }, sub: 'user-1' };
  const header = btoa('{"alg":"HS256","typ":"JWT"}');
  const body = btoa(JSON.stringify(payload));
  return {
    access_token: `${header}.${body}.sig`,
    profile: {
      sub: 'user-1',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      preferred_username: 'parzival',
    },
  };
}

describe('AuthContext lifecycle — getMe() after unmount (P1-6)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMeState.resolver = null;
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = craftOidcUser();
  });

  it('does not crash / warn when getMe resolves after provider unmount', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { unmount } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    unmount();

    // Now resolve getMe — the `.then` should bail out early due to mountedRef.
    // If the guard is missing, React will warn about setState on unmounted
    // component via console.error.
    expect(getMeState.resolver).not.toBeNull();
    await act(async () => {
      getMeState.resolver?.({ role_display_names: { viewer: 'Viewer' } });
      // Let microtasks flush.
      await Promise.resolve();
    });

    const unmountedWarning = consoleError.mock.calls.find((args) =>
      String(args[0]).includes('setState'),
    );
    expect(unmountedWarning).toBeUndefined();
    consoleError.mockRestore();
  });
});

describe('AuthContext lifecycle — setTokenRefresher stability (P1-7)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockOidcState.isAuthenticated = true;
    mockOidcState.user = craftOidcUser();
  });

  it('does not re-register the refresher on every render while signin* refs stay stable', () => {
    const { rerender } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    const initialCalls = setTokenRefresher.mock.calls.length;

    // 5 extra re-renders with the same `mockOidcState` object reference —
    // signinSilent and signinRedirect are the SAME function references.
    for (let i = 0; i < 5; i++) rerender();

    // Dep array [signinSilent, signinRedirect] should stay stable, so the
    // effect does not re-fire. Allow a tiny tolerance for StrictMode double-
    // invocation of effects in dev.
    expect(setTokenRefresher.mock.calls.length - initialCalls).toBeLessThanOrEqual(1);
  });
});
