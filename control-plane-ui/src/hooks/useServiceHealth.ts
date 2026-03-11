import { useState, useEffect, useCallback } from 'react';

type ServiceStatus = 'checking' | 'available' | 'unavailable';

interface UseServiceHealthResult {
  status: ServiceStatus;
  retry: () => void;
}

/**
 * Probes a URL to check if the service behind it is reachable.
 * Uses a HEAD request with a 5-second timeout.
 *
 * Same-origin URLs: follows redirects and checks if the response was redirected
 * to a different path (e.g., Grafana → /login). A redirect away from the
 * requested path means the service requires auth and is not directly embeddable.
 *
 * Cross-origin URLs: uses no-cors mode (opaque response = reachable).
 */
export function useServiceHealth(url: string): UseServiceHealthResult {
  const [status, setStatus] = useState<ServiceStatus>('checking');

  const checkHealth = useCallback(async () => {
    setStatus('checking');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    try {
      const isSameOrigin = url.startsWith('/') || url.startsWith(window.location.origin);

      if (isSameOrigin) {
        // Same-origin: follow redirects to detect auth redirect chains
        const response = await fetch(url, {
          method: 'HEAD',
          signal: controller.signal,
          mode: 'same-origin',
          redirect: 'follow',
        });

        if (response.ok) {
          // Check if we were redirected to a login page (auth redirect)
          if (response.redirected) {
            const responsePath = new URL(response.url, window.location.origin).pathname;
            if (responsePath.includes('/login')) {
              // Redirected to login — service needs auth, not embeddable
              setStatus('unavailable');
            } else {
              setStatus('available');
            }
          } else {
            setStatus('available');
          }
        } else if (response.status >= 500) {
          setStatus('unavailable');
        } else {
          // 4xx — service is up, may need auth but at least responding
          setStatus('available');
        }
      } else {
        // Cross-origin: no-cors mode, opaque response means reachable
        const response = await fetch(url, {
          method: 'HEAD',
          signal: controller.signal,
          mode: 'no-cors',
          redirect: 'manual',
        });

        if (response.type === 'opaque' || response.type === 'opaqueredirect' || response.ok) {
          setStatus('available');
        } else if (response.status >= 500) {
          setStatus('unavailable');
        } else {
          setStatus('available');
        }
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
