import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { usePlatformSettings, useUpdatePlatformSetting } from './usePlatformSettings';

vi.mock('../services/api', () => ({
  apiService: {
    getPlatformSettings: vi.fn(),
    updatePlatformSetting: vi.fn(),
  },
}));

import { apiService } from '../services/api';

const mockGetPlatformSettings = vi.mocked(apiService.getPlatformSettings);
const mockUpdatePlatformSetting = vi.mocked(apiService.updatePlatformSetting);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockSettingsResponse = {
  settings: [
    { key: 'maintenance_mode', value: 'false', category: 'general' },
    { key: 'max_tenants', value: '100', category: 'limits' },
  ],
  total: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('usePlatformSettings', () => {
  it('fetches platform settings', async () => {
    mockGetPlatformSettings.mockResolvedValue(mockSettingsResponse as any);

    const { result } = renderHook(() => usePlatformSettings(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPlatformSettings).toHaveBeenCalledWith(undefined);
    expect(result.current.data).toEqual(mockSettingsResponse);
  });

  it('fetches with category filter', async () => {
    mockGetPlatformSettings.mockResolvedValue(mockSettingsResponse as any);

    const { result } = renderHook(() => usePlatformSettings({ category: 'general' }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetPlatformSettings).toHaveBeenCalledWith({ category: 'general' });
  });

  it('respects enabled option', () => {
    renderHook(() => usePlatformSettings(undefined, { enabled: false }), {
      wrapper: createWrapper(),
    });
    expect(mockGetPlatformSettings).not.toHaveBeenCalled();
  });

  it('handles API error', async () => {
    mockGetPlatformSettings.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => usePlatformSettings(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('useUpdatePlatformSetting', () => {
  it('updates a setting successfully', async () => {
    const updatedSetting = { key: 'maintenance_mode', value: 'true', category: 'general' };
    mockUpdatePlatformSetting.mockResolvedValue(updatedSetting as any);

    const { result } = renderHook(() => useUpdatePlatformSetting(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ key: 'maintenance_mode', value: 'true' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockUpdatePlatformSetting).toHaveBeenCalledWith('maintenance_mode', 'true');
  });

  it('handles mutation error', async () => {
    mockUpdatePlatformSetting.mockRejectedValue(new Error('Forbidden'));

    const { result } = renderHook(() => useUpdatePlatformSetting(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ key: 'maintenance_mode', value: 'true' });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
