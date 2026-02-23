import { useState, useCallback, useRef, useEffect } from 'react';
import { useEvents } from './useEvents';
import { apiService } from '../services/api';
import type { DeploymentLog, DeploymentStatus, Event } from '../types';

const DEPLOY_EVENT_TYPES = ['deploy-started', 'deploy-progress', 'deploy-success', 'deploy-failed'];

interface DeployEventState {
  logs: DeploymentLog[];
  currentStep: string | null;
  status: DeploymentStatus | null;
}

interface UseDeployEventsOptions {
  tenantId: string;
  enabled?: boolean;
  onStatusChange?: (deploymentId: string, status: DeploymentStatus) => void;
}

export function useDeployEvents({
  tenantId,
  enabled = true,
  onStatusChange,
}: UseDeployEventsOptions) {
  const [deployStates, setDeployStates] = useState<Record<string, DeployEventState>>({});
  const onStatusChangeRef = useRef(onStatusChange);
  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);

  const handleEvent = useCallback((event: Event) => {
    const deploymentId = event.payload.deployment_id as string;
    if (!deploymentId) return;

    setDeployStates((prev) => {
      const existing = prev[deploymentId] || { logs: [], currentStep: null, status: null };

      if (event.type === 'deploy-started') {
        return {
          ...prev,
          [deploymentId]: { logs: [], currentStep: 'init', status: 'in_progress' },
        };
      }

      if (event.type === 'deploy-progress') {
        const log: DeploymentLog = {
          id: `${deploymentId}-${event.payload.seq}`,
          deployment_id: deploymentId,
          tenant_id: event.tenant_id,
          seq: (event.payload.seq as number) || existing.logs.length,
          level: (event.payload.level as DeploymentLog['level']) || 'info',
          step: event.payload.step as string | undefined,
          message: (event.payload.message as string) || '',
          created_at: event.timestamp,
        };
        return {
          ...prev,
          [deploymentId]: {
            logs: [...existing.logs, log],
            currentStep: log.step || existing.currentStep,
            status: 'in_progress',
          },
        };
      }

      if (event.type === 'deploy-success') {
        onStatusChangeRef.current?.(deploymentId, 'success');
        return {
          ...prev,
          [deploymentId]: { ...existing, currentStep: 'complete', status: 'success' },
        };
      }

      if (event.type === 'deploy-failed') {
        onStatusChangeRef.current?.(deploymentId, 'failed');
        return {
          ...prev,
          [deploymentId]: { ...existing, currentStep: null, status: 'failed' },
        };
      }

      return prev;
    });
  }, []);

  useEvents({ tenantId, eventTypes: DEPLOY_EVENT_TYPES, onEvent: handleEvent, enabled });

  const loadHistoricalLogs = useCallback(
    async (deploymentId: string) => {
      const result = await apiService.getDeploymentLogs(tenantId, deploymentId);
      setDeployStates((prev) => ({
        ...prev,
        [deploymentId]: {
          logs: result.items,
          currentStep: result.items[result.items.length - 1]?.step || null,
          status: prev[deploymentId]?.status || null,
        },
      }));
    },
    [tenantId]
  );

  return { deployStates, loadHistoricalLogs };
}
