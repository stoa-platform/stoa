import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { EnvironmentProvider, useEnvironment } from './EnvironmentContext';

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
});

describe('EnvironmentContext', () => {
  it('defaults to dev environment', () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    expect(result.current.activeEnvironment).toBe('dev');
    expect(result.current.activeConfig.name).toBe('dev');
    expect(result.current.activeConfig.label).toBe('Development');
  });

  it('restores environment from localStorage', () => {
    localStorage.setItem('stoa-active-environment', 'staging');

    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    expect(result.current.activeEnvironment).toBe('staging');
    expect(result.current.activeConfig.label).toBe('Staging');
  });

  it('falls back to dev for invalid localStorage value', () => {
    localStorage.setItem('stoa-active-environment', 'invalid');

    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    expect(result.current.activeEnvironment).toBe('dev');
  });

  it('switches environment and persists to localStorage', () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    act(() => {
      result.current.switchEnvironment('prod');
    });

    expect(result.current.activeEnvironment).toBe('prod');
    expect(result.current.activeConfig.label).toBe('Production');
    expect(localStorage.getItem('stoa-active-environment')).toBe('prod');
  });

  it('invalidates queries on environment switch', () => {
    const wrapper = createWrapper(); // Sets queryClient first
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useEnvironment(), { wrapper });
    invalidateSpy.mockClear(); // Clear any calls from initialization

    act(() => {
      result.current.switchEnvironment('staging');
    });

    expect(invalidateSpy).toHaveBeenCalled();
  });

  it('provides list of all environments', () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    expect(result.current.environments).toHaveLength(3);
    expect(result.current.environments.map((e) => e.name)).toEqual(['dev', 'staging', 'prod']);
  });

  it('throws when used outside provider', () => {
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => {
      renderHook(() => useEnvironment());
    }).toThrow('useEnvironment must be used within an EnvironmentProvider');

    consoleSpy.mockRestore();
  });

  it('environment configs have correct mode', () => {
    const { result } = renderHook(() => useEnvironment(), { wrapper: createWrapper() });

    const modes = Object.fromEntries(result.current.environments.map((e) => [e.name, e.mode]));
    expect(modes).toEqual({
      dev: 'full',
      staging: 'full',
      prod: 'read-only',
    });
  });
});
