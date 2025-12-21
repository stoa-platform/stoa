import { useEffect, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import type { Event } from '../types';

interface UseEventsOptions {
  tenantId: string;
  eventTypes?: string[];
  onEvent?: (event: Event) => void;
  enabled?: boolean;
}

export function useEvents({ tenantId, eventTypes, onEvent, enabled = true }: UseEventsOptions) {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);

  const handleEvent = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as Event;

      // Call custom handler
      onEvent?.(data);

      // Invalidate relevant queries based on event type
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
  }, [queryClient, tenantId, onEvent]);

  useEffect(() => {
    if (!enabled || !tenantId) return;

    // Create EventSource connection
    const eventSource = apiService.createEventSource(tenantId, eventTypes);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = handleEvent;

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error);
      // EventSource will automatically reconnect
    };

    return () => {
      eventSource.close();
      eventSourceRef.current = null;
    };
  }, [tenantId, eventTypes, enabled, handleEvent]);

  return {
    close: () => eventSourceRef.current?.close(),
  };
}
