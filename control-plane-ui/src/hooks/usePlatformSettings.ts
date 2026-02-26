/**
 * Platform Settings Hook (CAB-1454)
 *
 * React Query hooks for platform settings management.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import type { PlatformSettingsResponse, PlatformSetting } from '../types';

export function usePlatformSettings(
  params?: { category?: string },
  options?: { enabled?: boolean }
) {
  const { enabled = true } = options || {};

  return useQuery<PlatformSettingsResponse>({
    queryKey: ['platform-settings', params],
    queryFn: () => apiService.getPlatformSettings(params),
    enabled,
    staleTime: 5000,
  });
}

export function useUpdatePlatformSetting() {
  const queryClient = useQueryClient();

  return useMutation<PlatformSetting, Error, { key: string; value: string }>({
    mutationFn: ({ key, value }) => apiService.updatePlatformSetting(key, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['platform-settings'] });
    },
  });
}
