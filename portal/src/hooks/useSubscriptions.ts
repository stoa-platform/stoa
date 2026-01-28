// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * STOA Developer Portal - MCP Subscription Hooks
 *
 * React Query hooks for MCP subscription operations.
 * Uses MCP Gateway endpoints (mcp.gostoa.dev)
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
import type { MCPSubscription, MCPSubscriptionCreate, MCPSubscriptionConfig, APISubscription, KeyRotationResponse } from '../types';

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

// ============ Key Rotation Hooks (CAB-314) ============

/**
 * Hook to rotate API key with grace period
 *
 * Returns the new API key (shown only once!) and grace period info.
 * The old key remains valid for the grace period.
 */
export function useRotateApiKey() {
  const queryClient = useQueryClient();

  return useMutation<KeyRotationResponse, Error, { id: string; gracePeriodHours?: number }>({
    mutationFn: ({ id, gracePeriodHours }) =>
      subscriptionsService.rotateApiKey(id, gracePeriodHours ? { grace_period_hours: gracePeriodHours } : undefined),
    onSuccess: (_, { id }) => {
      // Invalidate subscriptions to reflect new key prefix
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['subscription', id] });
    },
  });
}

/**
 * Hook to get subscription with rotation info
 */
export function useSubscriptionRotationInfo(id: string | undefined) {
  return useQuery<MCPSubscription>({
    queryKey: ['subscription', id, 'rotation-info'],
    queryFn: () => subscriptionsService.getRotationInfo(id!),
    enabled: !!id,
    staleTime: 30 * 1000, // 30 seconds
  });
}

// ============ API Subscriptions (Control-Plane API) ============
// API Subscriptions (apps subscribing to REST APIs) are separate from MCP Subscriptions.
// Uses Control-Plane API endpoints (/v1/subscriptions)
// Reference: CAB-483

import {
  apiSubscriptionsService,
  CreateAPISubscriptionRequest,
  KeyRotationResponse as APIKeyRotationResponse,
} from '../services/apiSubscriptions';

export interface SubscribeToAPIRequest {
  applicationId: string;
  applicationName: string;
  apiId: string;
  apiName: string;
  apiVersion: string;
  tenantId: string;
  planId?: string;
  planName?: string;
}

export interface SubscribeToAPIResponse {
  subscription: APISubscription;
  apiKey: string; // Full API key - shown only once!
  apiKeyPrefix: string;
}

/**
 * Hook to subscribe an application to an API
 * Returns the subscription AND the API key (shown only once!)
 */
export function useSubscribe() {
  const queryClient = useQueryClient();

  return useMutation<SubscribeToAPIResponse, Error, SubscribeToAPIRequest>({
    mutationFn: async (data) => {
      const request: CreateAPISubscriptionRequest = {
        application_id: data.applicationId,
        application_name: data.applicationName,
        api_id: data.apiId,
        api_name: data.apiName,
        api_version: data.apiVersion,
        tenant_id: data.tenantId,
        plan_id: data.planId,
        plan_name: data.planName,
      };

      const response = await apiSubscriptionsService.createSubscription(request);

      // Return both the subscription info and the API key
      const subscription: APISubscription = {
        id: response.subscription_id,
        applicationId: data.applicationId,
        apiId: data.apiId,
        status: 'active',
        plan: 'free', // Default plan
        createdAt: new Date().toISOString(),
        expiresAt: response.expires_at || undefined,
      };

      return {
        subscription,
        apiKey: response.api_key,
        apiKeyPrefix: response.api_key_prefix,
      };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['my-api-subscriptions'] });
    },
  });
}

/**
 * Hook to get my API subscriptions
 */
export function useMyAPISubscriptions() {
  return useQuery<APISubscription[]>({
    queryKey: ['my-api-subscriptions'],
    queryFn: () => apiSubscriptionsService.getMySubscriptionsFormatted(),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get subscriptions for an application
 */
export function useApplicationSubscriptions(applicationId: string | undefined) {
  const { data: allSubscriptions, ...rest } = useMyAPISubscriptions();

  // Filter subscriptions by application ID
  const subscriptions = allSubscriptions?.filter(
    (sub) => sub.applicationId === applicationId
  );

  return {
    ...rest,
    data: subscriptions,
  };
}

/**
 * Hook to cancel an API subscription
 */
export function useCancelSubscription() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (subscriptionId) => apiSubscriptionsService.cancelSubscription(subscriptionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['my-api-subscriptions'] });
    },
  });
}

/**
 * Hook to rotate API key for an API subscription
 */
export function useRotateAPISubscriptionKey() {
  const queryClient = useQueryClient();

  return useMutation<APIKeyRotationResponse, Error, { id: string; gracePeriodHours?: number }>({
    mutationFn: ({ id, gracePeriodHours }) =>
      apiSubscriptionsService.rotateKey(id, gracePeriodHours ? { grace_period_hours: gracePeriodHours } : undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['my-api-subscriptions'] });
    },
  });
}
