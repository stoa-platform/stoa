/**
 * STOA Developer Portal - Subscription Hooks
 *
 * React Query hooks for API subscription operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { subscriptionsService, ListSubscriptionsParams, SubscribeToAPIRequest } from '../services/subscriptions';
import type { APISubscription, PaginatedResponse } from '../types';

/**
 * Hook to list user's subscriptions
 */
export function useSubscriptions(params?: ListSubscriptionsParams) {
  return useQuery<PaginatedResponse<APISubscription>>({
    queryKey: ['subscriptions', params],
    queryFn: () => subscriptionsService.listSubscriptions(params),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a single subscription by ID
 */
export function useSubscription(id: string | undefined) {
  return useQuery<APISubscription>({
    queryKey: ['subscription', id],
    queryFn: () => subscriptionsService.getSubscription(id!),
    enabled: !!id,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get subscriptions for an application
 */
export function useApplicationSubscriptions(applicationId: string | undefined) {
  return useQuery<APISubscription[]>({
    queryKey: ['subscriptions', 'application', applicationId],
    queryFn: () => subscriptionsService.getByApplication(applicationId!),
    enabled: !!applicationId,
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get subscription usage
 */
export function useSubscriptionUsage(id: string | undefined) {
  return useQuery<APISubscription['usage']>({
    queryKey: ['subscription', id, 'usage'],
    queryFn: () => subscriptionsService.getUsage(id!),
    enabled: !!id,
    staleTime: 10 * 1000, // 10 seconds - usage data should be fresher
    refetchInterval: 60 * 1000, // Auto-refresh every minute
  });
}

/**
 * Hook to subscribe to an API
 */
export function useSubscribe() {
  const queryClient = useQueryClient();

  return useMutation<APISubscription, Error, SubscribeToAPIRequest>({
    mutationFn: (data) => subscriptionsService.subscribe(data),
    onSuccess: (data) => {
      // Invalidate subscriptions list
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
      // Also invalidate application subscriptions
      queryClient.invalidateQueries({
        queryKey: ['subscriptions', 'application', data.applicationId],
      });
    },
  });
}

/**
 * Hook to cancel a subscription
 */
export function useCancelSubscription() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (id) => subscriptionsService.cancelSubscription(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
  });
}
