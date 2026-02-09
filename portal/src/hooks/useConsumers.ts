/**
 * STOA Developer Portal - Consumer Hooks
 *
 * React Query hooks for consumer operations (CAB-1121).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { consumersService, ListConsumersParams } from '../services/consumers';
import type {
  Consumer,
  ConsumerCreateRequest,
  ConsumerUpdateRequest,
  ConsumerCredentials,
  PaginatedResponse,
} from '../types';

/**
 * Hook to list consumers for a tenant
 */
export function useConsumers(tenantId: string | undefined, params?: ListConsumersParams) {
  return useQuery<PaginatedResponse<Consumer>>({
    queryKey: ['consumers', tenantId, params],
    queryFn: () => consumersService.listConsumers(tenantId!, params),
    enabled: !!tenantId,
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a single consumer by ID
 */
export function useConsumer(tenantId: string | undefined, consumerId: string | undefined) {
  return useQuery<Consumer>({
    queryKey: ['consumer', tenantId, consumerId],
    queryFn: () => consumersService.getConsumer(tenantId!, consumerId!),
    enabled: !!tenantId && !!consumerId,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to create a new consumer
 */
export function useCreateConsumer(tenantId: string) {
  const queryClient = useQueryClient();

  return useMutation<Consumer, Error, ConsumerCreateRequest>({
    mutationFn: (data) => consumersService.createConsumer(tenantId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
    },
  });
}

/**
 * Hook to update a consumer
 */
export function useUpdateConsumer(tenantId: string, consumerId: string) {
  const queryClient = useQueryClient();

  return useMutation<Consumer, Error, ConsumerUpdateRequest>({
    mutationFn: (data) => consumersService.updateConsumer(tenantId, consumerId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['consumer', tenantId, consumerId] });
    },
  });
}

/**
 * Hook to delete a consumer
 */
export function useDeleteConsumer(tenantId: string) {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (consumerId) => consumersService.deleteConsumer(tenantId, consumerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
    },
  });
}

/**
 * Hook to suspend a consumer
 */
export function useSuspendConsumer(tenantId: string) {
  const queryClient = useQueryClient();

  return useMutation<Consumer, Error, string>({
    mutationFn: (consumerId) => consumersService.suspendConsumer(tenantId, consumerId),
    onSuccess: (_, consumerId) => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['consumer', tenantId, consumerId] });
    },
  });
}

/**
 * Hook to activate a consumer
 */
export function useActivateConsumer(tenantId: string) {
  const queryClient = useQueryClient();

  return useMutation<Consumer, Error, string>({
    mutationFn: (consumerId) => consumersService.activateConsumer(tenantId, consumerId),
    onSuccess: (_, consumerId) => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['consumer', tenantId, consumerId] });
    },
  });
}

/**
 * Hook to block a consumer
 */
export function useBlockConsumer(tenantId: string) {
  const queryClient = useQueryClient();

  return useMutation<Consumer, Error, string>({
    mutationFn: (consumerId) => consumersService.blockConsumer(tenantId, consumerId),
    onSuccess: (_, consumerId) => {
      queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['consumer', tenantId, consumerId] });
    },
  });
}

/**
 * Hook to get consumer credentials
 */
export function useConsumerCredentials(
  tenantId: string | undefined,
  consumerId: string | undefined
) {
  return useQuery<ConsumerCredentials>({
    queryKey: ['consumer-credentials', tenantId, consumerId],
    queryFn: () => consumersService.getCredentials(tenantId!, consumerId!),
    enabled: false, // Only fetch on demand
    staleTime: 0, // Never cache credentials
  });
}
