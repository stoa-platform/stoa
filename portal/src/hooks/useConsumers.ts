/**
 * STOA Developer Portal - Consumer Hooks
 *
 * React Query hooks for consumer registration and management.
 *
 * Reference: CAB-1121 Phase 5
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { consumersService, ListConsumersParams } from '../services/consumers';
import type {
  Consumer,
  ConsumerCreate,
  ConsumerUpdate,
  ConsumerCredentials,
  ConsumerListResponse,
} from '../types';

/**
 * Hook to list consumers for a tenant
 */
export function useConsumers(tenantId: string | undefined, params?: ListConsumersParams) {
  return useQuery<ConsumerListResponse>({
    queryKey: ['consumers', tenantId, params],
    queryFn: () => consumersService.list(tenantId!, params),
    enabled: !!tenantId,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook to get a single consumer
 */
export function useConsumer(tenantId: string | undefined, consumerId: string | undefined) {
  return useQuery<Consumer>({
    queryKey: ['consumer', tenantId, consumerId],
    queryFn: () => consumersService.get(tenantId!, consumerId!),
    enabled: !!tenantId && !!consumerId,
    staleTime: 60 * 1000,
  });
}

/**
 * Hook to register a new consumer
 */
export function useRegisterConsumer() {
  const queryClient = useQueryClient();

  return useMutation<Consumer, Error, { tenantId: string; data: ConsumerCreate }>({
    mutationFn: ({ tenantId, data }) => consumersService.register(tenantId, data),
    onSuccess: (_data, { tenantId }) => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
    },
  });
}

/**
 * Hook to update a consumer
 */
export function useUpdateConsumer() {
  const queryClient = useQueryClient();

  return useMutation<
    Consumer,
    Error,
    { tenantId: string; consumerId: string; data: ConsumerUpdate }
  >({
    mutationFn: ({ tenantId, consumerId, data }) =>
      consumersService.update(tenantId, consumerId, data),
    onSuccess: (_data, { tenantId, consumerId }) => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['consumer', tenantId, consumerId] });
    },
  });
}

/**
 * Hook to get consumer credentials (one-time display)
 * This is a mutation because it regenerates the secret
 */
export function useConsumerCredentials() {
  return useMutation<ConsumerCredentials, Error, { tenantId: string; consumerId: string }>({
    mutationFn: ({ tenantId, consumerId }) => consumersService.getCredentials(tenantId, consumerId),
  });
}

/**
 * Hook to suspend a consumer
 */
export function useSuspendConsumer() {
  const queryClient = useQueryClient();

  return useMutation<Consumer, Error, { tenantId: string; consumerId: string }>({
    mutationFn: ({ tenantId, consumerId }) => consumersService.suspend(tenantId, consumerId),
    onSuccess: (_data, { tenantId }) => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
    },
  });
}

/**
 * Hook to activate a consumer
 */
export function useActivateConsumer() {
  const queryClient = useQueryClient();

  return useMutation<Consumer, Error, { tenantId: string; consumerId: string }>({
    mutationFn: ({ tenantId, consumerId }) => consumersService.activate(tenantId, consumerId),
    onSuccess: (_data, { tenantId }) => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
    },
  });
}
