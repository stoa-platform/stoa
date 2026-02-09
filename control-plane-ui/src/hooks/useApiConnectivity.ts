import { useQuery } from '@tanstack/react-query';
import { config } from '../config';

interface UseApiConnectivityResult {
  isConnected: boolean;
  isChecking: boolean;
}

/**
 * Polls the API health endpoint every 60 seconds.
 * Returns connectivity status for the global banner in Layout.
 */
export function useApiConnectivity(): UseApiConnectivityResult {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['api-connectivity'],
    queryFn: async () => {
      const response = await fetch(`${config.api.baseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      return response.json();
    },
    refetchInterval: 60_000,
    retry: 1,
    retryDelay: 5000,
  });

  return {
    isConnected: !isError && !!data,
    isChecking: isLoading,
  };
}
