import { useState, useEffect, useCallback, useRef } from 'react';

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
 *
 * P2-5 + P2-6: the probe is aborted on unmount (effect cleanup) and the
 * catch path distinguishes unmount-abort (no state change) from
 * timeout-abort (→ 'unavailable'), so a slow service is still correctly
 * reported as down while a fast unmount doesn't trigger setState warnings.
 */
export function useServiceHealth(url: string): UseServiceHealthResult {
  const [status, setStatus] = useState<ServiceStatus>('checking');
  const probeControllerRef = useRef<AbortController | null>(null);
  const abortedByUnmountRef = useRef(false);
  const mountedRef = useRef(true);

  const checkHealth = useCallback(async () => {
    // Abort any in-flight probe before starting a new one (retry path).
    probeControllerRef.current?.abort();

    const controller = new AbortController();
    probeControllerRef.current = controller;
    if (mountedRef.current) setStatus('checking');
    const timeout = setTimeout(() => controller.abort(), 5000);

    try {
      const isSameOrigin = url.startsWith('/') || url.startsWith(window.location.origin);

      if (isSameOrigin) {
        // Same-origin: follow redirects to detect auth redirect chains
        // eslint-disable-next-line no-restricted-globals -- liveness probe, no Bearer needed; auth handled via redirect detection
        const response = await fetch(url, {
          method: 'HEAD',
          signal: controller.signal,
          mode: 'same-origin',
          redirect: 'follow',
        });

        if (!mountedRef.current) return;

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
        // eslint-disable-next-line no-restricted-globals -- cross-origin probe, no-cors mode; Bearer token not applicable
        const response = await fetch(url, {
          method: 'HEAD',
          signal: controller.signal,
          mode: 'no-cors',
          redirect: 'manual',
        });

        if (!mountedRef.current) return;

        if (response.type === 'opaque' || response.type === 'opaqueredirect' || response.ok) {
          setStatus('available');
        } else if (response.status >= 500) {
          setStatus('unavailable');
        } else {
          setStatus('available');
        }
      }
    } catch (err) {
      // P2-5: only treat timeout-abort as 'unavailable'; unmount-abort is
      // a silent cancel. Any non-Abort error (network failure, CORS, etc.)
      // still maps to 'unavailable'.
      if (err instanceof DOMException && err.name === 'AbortError') {
        if (!abortedByUnmountRef.current && mountedRef.current) {
          setStatus('unavailable');
        }
        return;
      }
      if (mountedRef.current) setStatus('unavailable');
    } finally {
      clearTimeout(timeout);
    }
  }, [url]);

  useEffect(() => {
    mountedRef.current = true;
    abortedByUnmountRef.current = false;
    checkHealth();

    return () => {
      // P2-6: abort the in-flight probe on unmount so the catch path can
      // distinguish this from a timeout-abort and skip the final setState.
      mountedRef.current = false;
      abortedByUnmountRef.current = true;
      probeControllerRef.current?.abort();
      probeControllerRef.current = null;
    };
  }, [checkHealth]);

  return { status, retry: checkHealth };
}
