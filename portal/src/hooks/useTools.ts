/**
 * STOA Developer Portal - MCP Tools Hooks
 *
 * React Query hooks for MCP Tools operations via MCP Gateway.
 * These hooks enable both human users and AI agents to discover and invoke tools.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toolsService, ListToolsParams, ListToolsResponse } from '../services/tools';
import { subscriptionsService } from '../services/subscriptions';
import type { MCPTool, MCPToolInvocation, MCPServerInfo, MCPSubscription } from '../types';

/**
 * Hook to list MCP tools from MCP Gateway
 *
 * @param params - Optional filters (tag, tenant_id) and pagination (cursor, limit)
 */
export function useTools(params?: ListToolsParams) {
  return useQuery<ListToolsResponse>({
    queryKey: ['tools', params],
    queryFn: () => toolsService.listTools(params),
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get a single tool by name
 *
 * @param name - Tool name (e.g., "tenant-acme__create-order")
 */
export function useTool(name: string | undefined) {
  return useQuery<MCPTool>({
    queryKey: ['tool', name],
    queryFn: () => toolsService.getTool(name!),
    enabled: !!name,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get tools by tag (category)
 *
 * @param tag - Tag to filter by
 */
export function useToolsByTag(tag: string | undefined) {
  return useQuery<MCPTool[]>({
    queryKey: ['tools', 'tag', tag],
    queryFn: () => toolsService.getByTag(tag!),
    enabled: !!tag,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to get all available tags (categories)
 */
export function useToolTags() {
  return useQuery<string[]>({
    queryKey: ['tools', 'tags'],
    queryFn: () => toolsService.getTags(),
    staleTime: 5 * 60 * 1000, // 5 minutes - tags don't change often
  });
}

/**
 * Alias for useToolTags - for backward compatibility with pages using "categories"
 */
export function useToolCategories() {
  return useToolTags();
}

/**
 * Hook to get a tool's input schema
 *
 * @param name - Tool name
 */
export function useToolSchema(name: string | undefined) {
  const toolQuery = useTool(name);
  return {
    ...toolQuery,
    data: toolQuery.data?.inputSchema,
  };
}

/**
 * Hook to subscribe to a tool
 * Returns the subscription AND the API key (shown only once!)
 *
 * Reference: Linear CAB-292
 */
export function useSubscribeToTool() {
  const queryClient = useQueryClient();

  return useMutation<
    { subscription: MCPSubscription; api_key: string },
    Error,
    { toolId: string; plan: 'free' | 'basic' | 'premium' }
  >({
    mutationFn: async ({ toolId, plan }) => {
      const response = await subscriptionsService.createSubscription({
        tool_id: toolId,
        plan,
      });
      return response;
    },
    onSuccess: () => {
      // Invalidate subscriptions list to show new subscription
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
  });
}

/**
 * Hook to get MCP server info
 */
export function useMCPServerInfo() {
  return useQuery<MCPServerInfo>({
    queryKey: ['mcp', 'serverInfo'],
    queryFn: () => toolsService.getServerInfo(),
    staleTime: 10 * 60 * 1000, // 10 minutes - server info doesn't change often
  });
}

/**
 * Hook to invoke a tool
 *
 * This is the main hook for AI agents to execute platform operations.
 */
export function useInvokeTool() {
  return useMutation<MCPToolInvocation, Error, { name: string; args: Record<string, unknown> }>({
    mutationFn: ({ name, args }) => toolsService.invokeTool(name, args),
    onSuccess: (result) => {
      // Log successful invocation for audit
      console.log('Tool invoked successfully:', result.toolName);
      // Optionally invalidate related queries based on the tool that was invoked
    },
    onError: (error) => {
      console.error('Tool invocation failed:', error);
    },
  });
}

/**
 * Hook to check MCP Gateway health
 */
export function useMCPHealth() {
  return useQuery<{ status: string }>({
    queryKey: ['mcp', 'health'],
    queryFn: () => toolsService.checkHealth(),
    staleTime: 30 * 1000, // 30 seconds
    refetchInterval: 60 * 1000, // Refetch every minute
  });
}

// Re-export types for convenience
export type { ListToolsParams, ListToolsResponse };
