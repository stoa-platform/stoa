import { useState, useEffect, useCallback } from 'react';

type ServiceStatus = 'checking' | 'available' | 'unavailable';

interface UseServiceHealthResult {
  status: ServiceStatus;
  retry: () => void;
}

/**
 * Probes a URL to check if the service behind it is reachable.
 * Uses a HEAD request with a 5-second timeout.
 * Same-origin URLs get a real status code check; cross-origin uses no-cors mode.
 */
export function useServiceHealth(url: string): UseServiceHealthResult {
  const [status, setStatus] = useState<ServiceStatus>('checking');

  const checkHealth = useCallback(async () => {
    setStatus('checking');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    try {
      const isSameOrigin = url.startsWith('/') || url.startsWith(window.location.origin);
      const response = await fetch(url, {
        method: 'HEAD',
        signal: controller.signal,
        mode: isSameOrigin ? 'same-origin' : 'no-cors',
      });

      // no-cors returns opaque response (status 0) — treat as available
      if (response.type === 'opaque' || response.ok) {
        setStatus('available');
      } else if (response.status >= 500) {
        setStatus('unavailable');
      } else {
        // 4xx etc — service is up, just may need auth
        setStatus('available');
      }
    } catch {
      setStatus('unavailable');
    } finally {
      clearTimeout(timeout);
    }
  }, [url]);

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  return { status, retry: checkHealth };
}
