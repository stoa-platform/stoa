import { useCallback, useEffect, useRef, useState } from 'react';
import { apiService } from '@/services/api';
import type { DeployEventType, DeployLogEntry } from '@/types';

interface UseDeployEventsOptions {
  tenantId: string | undefined;
  deploymentId?: string;
  enabled?: boolean;
}

interface DeployEventsState {
  logs: DeployLogEntry[];
  status: 'idle' | 'connecting' | 'connected' | 'disconnected';
  lastEvent: DeployEventType | null;
}

const DEPLOY_EVENT_TYPES: DeployEventType[] = [
  'deploy-started',
  'deploy-progress',
  'deploy-success',
  'deploy-failed',
];

export function useDeployEvents({
  tenantId,
  deploymentId,
  enabled = true,
}: UseDeployEventsOptions) {
  const [state, setState] = useState<DeployEventsState>({
    logs: [],
    status: 'idle',
    lastEvent: null,
  });
  const esRef = useRef<EventSource | null>(null);

  const disconnect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setState((prev) => ({ ...prev, status: 'disconnected' }));
  }, []);

  const clearLogs = useCallback(() => {
    setState({ logs: [], status: 'idle', lastEvent: null });
  }, []);

  useEffect(() => {
    if (!tenantId || !enabled) return;

    setState((prev) => ({ ...prev, status: 'connecting' }));
    const es = apiService.createEventSource(tenantId, DEPLOY_EVENT_TYPES);
    esRef.current = es;

    es.onopen = () => {
      setState((prev) => ({ ...prev, status: 'connected' }));
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Filter by deploymentId if specified
        if (deploymentId && data.deployment_id && data.deployment_id !== deploymentId) {
          return;
        }
        setState((prev) => ({
          ...prev,
          logs: [...prev.logs, data as DeployLogEntry],
          lastEvent: (event.type as DeployEventType) || 'deploy-progress',
        }));
      } catch {
        // Ignore parse errors (e.g. heartbeat)
      }
    };

    // Listen for named events
    for (const eventType of DEPLOY_EVENT_TYPES) {
      es.addEventListener(eventType, (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          if (deploymentId && data.deployment_id && data.deployment_id !== deploymentId) {
            return;
          }
          setState((prev) => ({
            ...prev,
            logs: [...prev.logs, data as DeployLogEntry],
            lastEvent: eventType,
          }));
        } catch {
          // Ignore parse errors
        }
      });
    }

    es.onerror = () => {
      setState((prev) => ({ ...prev, status: 'disconnected' }));
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [tenantId, deploymentId, enabled]);

  return { ...state, disconnect, clearLogs };
}
