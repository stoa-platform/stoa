import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { openEventStream, type SseConnection, type SseEvent } from '../services/http';
import type { Event } from '../types';

interface UseEventsOptions {
  tenantId: string;
  eventTypes?: string[];
  onEvent?: (event: Event) => void;
  enabled?: boolean;
}

// P2-8: minimal runtime shape guard on parsed SSE payloads. We vouch only
// for a string `type` field here; the switch below narrows further, and
// unknown types are dropped rather than forwarded to callers.
function isValidEvent(x: unknown): x is Event {
  return (
    !!x && typeof x === 'object' && 'type' in x && typeof (x as { type: unknown }).type === 'string'
  );
}

export function useEvents({ tenantId, eventTypes, onEvent, enabled = true }: UseEventsOptions) {
  const queryClient = useQueryClient();
  const connectionRef = useRef<SseConnection | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastError, setLastError] = useState<unknown>(null);

  // P0-8: stabilize eventTypes identity across renders when content is
  // unchanged. JSON.stringify is robust even if event types contained commas
  // (join(',') would collide on a=['x,y'] vs a=['x','y']).
  const eventTypesKey = useMemo(() => JSON.stringify(eventTypes ?? []), [eventTypes]);
  const stableEventTypes = useMemo(
    () => eventTypes ?? [],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional content-based stabilization
    [eventTypesKey]
  );

  const handleEvent = useCallback(
    (event: SseEvent) => {
      try {
        const parsed: unknown = JSON.parse(event.data);
        // P2-8: minimal type guard. We only vouch for `type: string`; the
        // caller's `onEvent` is invoked only for whitelisted event types,
        // so an unknown payload shape can't propagate past this boundary.
        if (!isValidEvent(parsed)) {
          if (import.meta.env.DEV) {
            // P2-9: gate residual diagnostic behind DEV to avoid leaking
            // parser state to end-user browser consoles in prod.
            console.warn('SSE: dropped event with unexpected shape', parsed);
          }
          return;
        }

        switch (parsed.type) {
          case 'api-created':
          case 'api-updated':
          case 'api-deleted':
            onEvent?.(parsed);
            queryClient.invalidateQueries({ queryKey: ['apis', tenantId] });
            break;
          case 'deploy-started':
          case 'deploy-progress':
          case 'deploy-success':
          case 'deploy-failed':
            onEvent?.(parsed);
            queryClient.invalidateQueries({ queryKey: ['deployments', tenantId] });
            queryClient.invalidateQueries({ queryKey: ['apis', tenantId] });
            break;
          case 'app-created':
          case 'app-updated':
          case 'app-deleted':
            onEvent?.(parsed);
            queryClient.invalidateQueries({ queryKey: ['applications', tenantId] });
            break;
          case 'tenant-created':
          case 'tenant-updated':
            onEvent?.(parsed);
            queryClient.invalidateQueries({ queryKey: ['tenants'] });
            break;
          default:
            // Unknown event type — drop silently (or log in DEV).
            if (import.meta.env.DEV) {
              console.warn('SSE: dropped unknown event type', parsed.type);
            }
        }
      } catch (error) {
        // P2-9: parse failure is diagnostic only, silence in prod.
        if (import.meta.env.DEV) console.error('Failed to parse event:', error);
      }
    },
    [queryClient, tenantId, onEvent]
  );

  useEffect(() => {
    if (!enabled || !tenantId) return;

    const connection = openEventStream(tenantId, stableEventTypes, {
      onOpen: () => {
        setIsConnected(true);
        setLastError(null);
      },
      onMessage: handleEvent,
      onError: (err) => {
        setIsConnected(false);
        setLastError(err);
      },
    });
    connectionRef.current = connection;

    return () => {
      connection.close();
      connectionRef.current = null;
      setIsConnected(false);
    };
  }, [tenantId, enabled, handleEvent, stableEventTypes]);

  return {
    close: () => connectionRef.current?.close(),
    isConnected,
    lastError,
  };
}
