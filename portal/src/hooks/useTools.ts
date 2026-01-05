/**
 * STOA Developer Portal - MCP Tools Hooks
 *
 * React Query hooks for MCP Tools operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolsService, ListToolsParams, SubscribeToToolRequest } from '../services/tools';
import type { MCPTool, Subscription, PaginatedResponse } from '../types';

/**
 * Hook to list MCP tools
 */
export function useTools(params?: ListToolsParams) {
  return useQuery<PaginatedResponse<MCPTool>>({
    queryKey: ['tools', params],
    queryFn: () => toolsService.listTools(params),
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get a single tool by ID
 */
export function useTool(id: string | undefined) {
  return useQuery<MCPTool>({
    queryKey: ['tool', id],
    queryFn: () => toolsService.getTool(id!),
    enabled: !!id,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get tools by category
 */
export function useToolsByCategory(category: string | undefined) {
  return useQuery<MCPTool[]>({
    queryKey: ['tools', 'category', category],
    queryFn: () => toolsService.getByCategory(category!),
    enabled: !!category,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get tool categories
 */
export function useToolCategories() {
  return useQuery<string[]>({
    queryKey: ['tools', 'categories'],
    queryFn: () => toolsService.getCategories(),
    staleTime: 5 * 60 * 1000, // 5 minutes - categories don't change often
  });
}

/**
 * Hook to get tool input schema
 */
export function useToolSchema(id: string | undefined) {
  return useQuery<object>({
    queryKey: ['tool', id, 'schema'],
    queryFn: () => toolsService.getInputSchema(id!),
    enabled: !!id,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to get user's tool subscriptions
 */
export function useToolSubscriptions() {
  return useQuery<PaginatedResponse<Subscription>>({
    queryKey: ['toolSubscriptions'],
    queryFn: () => toolsService.getSubscriptions(),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a single tool subscription
 */
export function useToolSubscription(id: string | undefined) {
  return useQuery<Subscription>({
    queryKey: ['toolSubscription', id],
    queryFn: () => toolsService.getSubscription(id!),
    enabled: !!id,
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to subscribe to a tool
 */
export function useSubscribeToTool() {
  const queryClient = useQueryClient();

  return useMutation<Subscription, Error, SubscribeToToolRequest>({
    mutationFn: (data) => toolsService.subscribe(data),
    onSuccess: () => {
      // Invalidate tool subscriptions list
      queryClient.invalidateQueries({ queryKey: ['toolSubscriptions'] });
      // Invalidate general subscriptions list (for MySubscriptions page)
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
  });
}

/**
 * Hook to cancel a tool subscription
 */
export function useCancelToolSubscription() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (id) => toolsService.cancelSubscription(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['toolSubscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
  });
}
