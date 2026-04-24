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
        const data = JSON.parse(event.data) as Event;

        onEvent?.(data);

        switch (data.type) {
          case 'api-created':
          case 'api-updated':
          case 'api-deleted':
            queryClient.invalidateQueries({ queryKey: ['apis', tenantId] });
            break;
          case 'deploy-started':
          case 'deploy-progress':
          case 'deploy-success':
          case 'deploy-failed':
            queryClient.invalidateQueries({ queryKey: ['deployments', tenantId] });
            queryClient.invalidateQueries({ queryKey: ['apis', tenantId] });
            break;
          case 'app-created':
          case 'app-updated':
          case 'app-deleted':
            queryClient.invalidateQueries({ queryKey: ['applications', tenantId] });
            break;
          case 'tenant-created':
          case 'tenant-updated':
            queryClient.invalidateQueries({ queryKey: ['tenants'] });
            break;
        }
      } catch (error) {
        console.error('Failed to parse event:', error);
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
