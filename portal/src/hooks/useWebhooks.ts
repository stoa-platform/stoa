// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * STOA Developer Portal - Webhook Hooks (CAB-315)
 *
 * React Query hooks for webhook operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  webhooksService,
  WebhookListResponse,
  WebhookDeliveryListResponse,
  EventTypesResponse,
} from '../services/webhooks';
import type {
  TenantWebhook,
  WebhookCreate,
  WebhookUpdate,
  WebhookTestResponse,
  WebhookDelivery,
} from '../types';

/**
 * Hook to get available webhook event types
 */
export function useWebhookEventTypes(tenantId: string | undefined) {
  return useQuery<EventTypesResponse>({
    queryKey: ['webhooks', 'event-types', tenantId],
    queryFn: () => webhooksService.getEventTypes(tenantId!),
    enabled: !!tenantId,
    staleTime: 5 * 60 * 1000, // 5 minutes - event types don't change often
  });
}

/**
 * Hook to list webhooks for a tenant
 */
export function useWebhooks(tenantId: string | undefined, enabledOnly?: boolean) {
  return useQuery<WebhookListResponse>({
    queryKey: ['webhooks', tenantId, { enabledOnly }],
    queryFn: () => webhooksService.listWebhooks(tenantId!, enabledOnly),
    enabled: !!tenantId,
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a specific webhook
 */
export function useWebhook(tenantId: string | undefined, webhookId: string | undefined) {
  return useQuery<TenantWebhook>({
    queryKey: ['webhooks', tenantId, webhookId],
    queryFn: () => webhooksService.getWebhook(tenantId!, webhookId!),
    enabled: !!tenantId && !!webhookId,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to create a webhook
 */
export function useCreateWebhook() {
  const queryClient = useQueryClient();

  return useMutation<TenantWebhook, Error, { tenantId: string; data: WebhookCreate }>({
    mutationFn: ({ tenantId, data }) => webhooksService.createWebhook(tenantId, data),
    onSuccess: (_, { tenantId }) => {
      queryClient.invalidateQueries({ queryKey: ['webhooks', tenantId] });
    },
  });
}

/**
 * Hook to update a webhook
 */
export function useUpdateWebhook() {
  const queryClient = useQueryClient();

  return useMutation<
    TenantWebhook,
    Error,
    { tenantId: string; webhookId: string; data: WebhookUpdate }
  >({
    mutationFn: ({ tenantId, webhookId, data }) =>
      webhooksService.updateWebhook(tenantId, webhookId, data),
    onSuccess: (_, { tenantId, webhookId }) => {
      queryClient.invalidateQueries({ queryKey: ['webhooks', tenantId] });
      queryClient.invalidateQueries({ queryKey: ['webhooks', tenantId, webhookId] });
    },
  });
}

/**
 * Hook to delete a webhook
 */
export function useDeleteWebhook() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, { tenantId: string; webhookId: string }>({
    mutationFn: ({ tenantId, webhookId }) =>
      webhooksService.deleteWebhook(tenantId, webhookId),
    onSuccess: (_, { tenantId }) => {
      queryClient.invalidateQueries({ queryKey: ['webhooks', tenantId] });
    },
  });
}

/**
 * Hook to test a webhook
 */
export function useTestWebhook() {
  return useMutation<
    WebhookTestResponse,
    Error,
    { tenantId: string; webhookId: string; eventType?: string }
  >({
    mutationFn: ({ tenantId, webhookId, eventType }) =>
      webhooksService.testWebhook(tenantId, webhookId, eventType),
  });
}

/**
 * Hook to get webhook deliveries
 */
export function useWebhookDeliveries(
  tenantId: string | undefined,
  webhookId: string | undefined,
  limit?: number
) {
  return useQuery<WebhookDeliveryListResponse>({
    queryKey: ['webhooks', tenantId, webhookId, 'deliveries', { limit }],
    queryFn: () => webhooksService.getDeliveries(tenantId!, webhookId!, limit),
    enabled: !!tenantId && !!webhookId,
    staleTime: 30 * 1000, // 30 seconds
    refetchInterval: 30 * 1000, // Refetch every 30 seconds
  });
}

/**
 * Hook to retry a failed delivery
 */
export function useRetryDelivery() {
  const queryClient = useQueryClient();

  return useMutation<
    WebhookDelivery,
    Error,
    { tenantId: string; webhookId: string; deliveryId: string }
  >({
    mutationFn: ({ tenantId, webhookId, deliveryId }) =>
      webhooksService.retryDelivery(tenantId, webhookId, deliveryId),
    onSuccess: (_, { tenantId, webhookId }) => {
      queryClient.invalidateQueries({
        queryKey: ['webhooks', tenantId, webhookId, 'deliveries'],
      });
    },
  });
}
