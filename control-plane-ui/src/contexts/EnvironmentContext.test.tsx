import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { EnvironmentProvider, useEnvironment } from './EnvironmentContext';

// Mock react-oidc-context
const mockOidcAuth = {
  user: { access_token: 'test-token-123' },
  isAuthenticated: true,
  isLoading: false,
};

vi.mock('react-oidc-context', () => ({
  useAuth: () => mockOidcAuth,
}));

// Mock config
vi.mock('../config', () => ({
  config: {
    api: { baseUrl: 'https://api.test.dev' },
  },
}));

// Mock fetch
const mockEnvironmentsResponse = {
  environments: [
    {
      name: 'dev',
      label: 'Development',
      mode: 'full',
      color: '#22c55e',
      endpoints: {
        api_url: 'https://api.dev.gostoa.dev',
        keycloak_url: 'https://auth.dev.gostoa.dev',
        keycloak_realm: 'stoa',
        mcp_url: 'https://mcp.dev.gostoa.dev',
      },
      is_current: false,
    },
    {
      name: 'staging',
      label: 'Staging',
      mode: 'full',
      color: '#f59e0b',
      endpoints: {
        api_url: 'https://api.staging.gostoa.dev',
        keycloak_url: 'https://auth.staging.gostoa.dev',
        keycloak_realm: 'stoa',
        mcp_url: 'https://mcp.staging.gostoa.dev',
      },
      is_current: false,
    },
    {
      name: 'production',
      label: 'Production',
      mode: 'read-only',
      color: '#ef4444',
      endpoints: {
        api_url: 'https://api.gostoa.dev',
        keycloak_url: 'https://auth.gostoa.dev',
        keycloak_realm: 'stoa',
        mcp_url: 'https://mcp.gostoa.dev',
      },
      is_current: true,
    },
  ],
  current: 'production',
};

let queryClient: QueryClient;

function createWrapper() {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(EnvironmentProvider, null, children)
    );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(mockEnvironmentsResponse),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('EnvironmentContext', () => {
  it('defaults to dev environment', () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    expect(result.current.activeEnvironment).toBe('dev');
  });

  it('fetches environments from API', async () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(global.fetch).toHaveBeenCalledWith('https://api.test.dev/v1/environments', {
      headers: { Authorization: 'Bearer test-token-123' },
    });
    expect(result.current.environments).toHaveLength(3);
  });

  it('restores environment from localStorage', async () => {
    localStorage.setItem('stoa-active-environment', 'staging');

    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.activeEnvironment).toBe('staging');
    expect(result.current.activeConfig.label).toBe('Staging');
  });

  it('falls back to dev for invalid localStorage value', () => {
    localStorage.setItem('stoa-active-environment', 'invalid');

    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    expect(result.current.activeEnvironment).toBe('dev');
  });

  it('switches environment and persists to localStorage', async () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    act(() => {
      result.current.switchEnvironment('prod');
    });

    expect(result.current.activeEnvironment).toBe('prod');
    expect(result.current.activeConfig.label).toBe('Production');
    expect(localStorage.getItem('stoa-active-environment')).toBe('prod');
  });

  it('invalidates queries on environment switch', async () => {
    const wrapper = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useEnvironment(), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    invalidateSpy.mockClear();

    act(() => {
      result.current.switchEnvironment('staging');
    });

    expect(invalidateSpy).toHaveBeenCalled();
  });

  it('provides list of all environments', async () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.environments).toHaveLength(3);
    expect(result.current.environments.map((e) => e.name)).toEqual(['dev', 'staging', 'prod']);
  });

  it('throws when used outside provider', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => {
      renderHook(() => useEnvironment());
    }).toThrow('useEnvironment must be used within an EnvironmentProvider');

    consoleSpy.mockRestore();
  });

  it('environment configs have correct mode', async () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    const devConfig = result.current.environments.find((e) => e.name === 'dev');
    const stagingConfig = result.current.environments.find((e) => e.name === 'staging');
    const prodConfig = result.current.environments.find((e) => e.name === 'prod');

    expect(devConfig?.mode).toBe('full');
    expect(stagingConfig?.mode).toBe('full');
    expect(prodConfig?.mode).toBe('read-only');
  });

  it('provides endpoints for active environment', async () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.endpoints).toBeTruthy();
    expect(result.current.endpoints?.api_url).toBe('https://api.dev.gostoa.dev');
  });

  it('falls back to defaults when API fails', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network error');
    expect(result.current.environments).toHaveLength(3);
    expect(result.current.activeEnvironment).toBe('dev');
  });

  it('does not fetch when not authenticated', async () => {
    mockOidcAuth.user = null as unknown as typeof mockOidcAuth.user;

    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(global.fetch).not.toHaveBeenCalled();

    // Restore
    mockOidcAuth.user = { access_token: 'test-token-123' };
  });

  it('maps "production" API name to "prod" environment key', async () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // API returns "production" but it should be mapped to "prod"
    const prodEnv = result.current.environments.find((e) => e.name === 'prod');
    expect(prodEnv).toBeTruthy();
    expect(prodEnv?.label).toBe('Production');
    expect(prodEnv?.endpoints?.api_url).toBe('https://api.gostoa.dev');
  });
});
