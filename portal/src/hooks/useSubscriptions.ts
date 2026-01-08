/**
 * STOA Developer Portal - MCP Subscription Hooks
 *
 * React Query hooks for MCP subscription operations.
 * Uses MCP Gateway endpoints (mcp.stoa.cab-i.com)
 *
 * Reference: Linear CAB-247
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  subscriptionsService,
  ListSubscriptionsParams,
  SubscriptionsListResponse,
  CreateSubscriptionResponse,
  RevealKeyResponse,
  ToggleTotpResponse,
} from '../services/subscriptions';
import type { MCPSubscription, MCPSubscriptionCreate, MCPSubscriptionConfig, APISubscription } from '../types';

/**
 * Hook to list user's MCP subscriptions
 */
export function useSubscriptions(params?: ListSubscriptionsParams) {
  return useQuery<SubscriptionsListResponse>({
    queryKey: ['subscriptions', params],
    queryFn: () => subscriptionsService.listSubscriptions(params),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a single subscription by ID
 */
export function useSubscription(id: string | undefined) {
  return useQuery<MCPSubscription>({
    queryKey: ['subscription', id],
    queryFn: () => subscriptionsService.getSubscription(id!),
    enabled: !!id,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get my subscriptions (convenience wrapper)
 */
export function useMySubscriptions() {
  return useQuery<MCPSubscription[]>({
    queryKey: ['subscriptions', 'my'],
    queryFn: () => subscriptionsService.getMySubscriptions(),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to create a subscription
 * Returns the subscription AND the API key (shown only once!)
 */
export function useCreateSubscription() {
  const queryClient = useQueryClient();

  return useMutation<CreateSubscriptionResponse, Error, MCPSubscriptionCreate>({
    mutationFn: (data) => subscriptionsService.createSubscription(data),
    onSuccess: () => {
      // Invalidate subscriptions list
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
  });
}

/**
 * Hook to revoke a subscription
 */
export function useRevokeSubscription() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (id) => subscriptionsService.revokeSubscription(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
  });
}

/**
 * Hook to regenerate API key for a subscription
 */
export function useRegenerateApiKey() {
  const queryClient = useQueryClient();

  return useMutation<{ api_key: string }, Error, string>({
    mutationFn: (id) => subscriptionsService.regenerateApiKey(id),
    onSuccess: (_, id) => {
      // Invalidate specific subscription
      queryClient.invalidateQueries({ queryKey: ['subscription', id] });
    },
  });
}

/**
 * Hook to get claude_desktop_config.json export
 */
export function useSubscriptionConfig(id: string | undefined) {
  return useQuery<MCPSubscriptionConfig>({
    queryKey: ['subscription', id, 'config'],
    queryFn: () => subscriptionsService.getConfigExport(id!),
    enabled: !!id,
    staleTime: 5 * 60 * 1000, // 5 minutes - config doesn't change often
  });
}

/**
 * Hook to reveal API key (requires 2FA if enabled)
 *
 * ⚠️ If TOTP is required but token doesn't have TOTP ACR, returns 403.
 * The UI should handle step-up authentication flow.
 */
export function useRevealApiKey() {
  return useMutation<RevealKeyResponse, Error, { id: string; totpCode?: string }>({
    mutationFn: ({ id, totpCode }) => subscriptionsService.revealApiKey(id, totpCode),
  });
}

/**
 * Hook to toggle TOTP requirement for key reveal
 */
export function useToggleTotpRequirement() {
  const queryClient = useQueryClient();

  return useMutation<ToggleTotpResponse, Error, { id: string; enabled: boolean }>({
    mutationFn: ({ id, enabled }) => subscriptionsService.toggleTotpRequirement(id, enabled),
    onSuccess: (_, { id }) => {
      // Invalidate subscriptions to reflect new totp_required status
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['subscription', id] });
    },
  });
}

// ============ API Subscriptions (Control-Plane API) ============
// These are placeholder hooks for the API Catalog feature.
// API Subscriptions (apps subscribing to APIs) are separate from MCP Subscriptions (users subscribing to MCP tools).
// TODO: Implement these when Control-Plane API adds /v1/subscriptions endpoints

interface SubscribeToAPIRequest {
  applicationId: string;
  apiId: string;
  plan: 'free' | 'basic' | 'premium' | 'enterprise';
}

/**
 * Hook to subscribe an application to an API
 * NOTE: Placeholder - backend endpoint not yet implemented
 */
export function useSubscribe() {
  const queryClient = useQueryClient();

  return useMutation<APISubscription, Error, SubscribeToAPIRequest>({
    mutationFn: async (data) => {
      // TODO: Implement when Control-Plane API adds /v1/subscriptions endpoint
      console.warn('API subscriptions not yet implemented. Request:', data);
      throw new Error('API subscriptions feature not yet available. Coming soon!');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-subscriptions'] });
    },
  });
}

/**
 * Hook to get subscriptions for an application
 * NOTE: Placeholder - backend endpoint not yet implemented
 */
export function useApplicationSubscriptions(applicationId: string | undefined) {
  return useQuery<APISubscription[]>({
    queryKey: ['api-subscriptions', 'application', applicationId],
    queryFn: async () => {
      // TODO: Implement when Control-Plane API adds /v1/applications/{id}/subscriptions endpoint
      console.warn('Application subscriptions not yet implemented for:', applicationId);
      return [];
    },
    enabled: !!applicationId,
  });
}

/**
 * Hook to cancel an API subscription
 * NOTE: Placeholder - backend endpoint not yet implemented
 */
export function useCancelSubscription() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: async (subscriptionId) => {
      // TODO: Implement when Control-Plane API adds DELETE /v1/subscriptions/{id} endpoint
      console.warn('Cancel API subscription not yet implemented. ID:', subscriptionId);
      throw new Error('Cancel subscription feature not yet available. Coming soon!');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-subscriptions'] });
    },
  });
}
