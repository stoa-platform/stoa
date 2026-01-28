// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * MCP Tools API Service
 *
 * Client for accessing MCP tools via the Control-Plane-API.
 * Routes through webMethods Gateway for OIDC authentication.
 *
 * Flow: Console UI → webMethods Gateway → Control-Plane-API → MCP Gateway
 *
 * This approach ensures:
 * - Consistent authentication via webMethods Gateway
 * - Single API entry point for the Console UI
 * - Centralized logging and monitoring
 */

import { apiService } from './api';
import type {
  MCPTool,
  ListToolsResponse,
  ToolUsageSummary,
  ToolSubscription,
  ToolSubscriptionCreate,
} from '../types';

/**
 * MCP Tools Service
 *
 * Provides access to AI tools catalog via Control-Plane-API proxy.
 * All calls go through webMethods Gateway with OIDC authentication.
 */
class MCPToolsService {
  // ==========================================================================
  // Tools Catalog (via Control-Plane-API proxy to MCP Gateway)
  // ==========================================================================

  /**
   * List all available tools with optional filtering.
   * Endpoint: GET /v1/mcp/tools
   */
  async getTools(params?: {
    tenant?: string;
    tag?: string;
    search?: string;
    cursor?: string;
    limit?: number;
  }): Promise<ListToolsResponse> {
    const { data } = await apiService.get('/v1/mcp/tools', {
      params: {
        tenant_id: params?.tenant,
        tag: params?.tag,
        search: params?.search,
        cursor: params?.cursor,
        limit: params?.limit || 20,
      },
    });
    return data;
  }

  /**
   * Get a specific tool by name.
   * Endpoint: GET /v1/mcp/tools/{name}
   */
  async getTool(toolName: string): Promise<MCPTool> {
    const { data } = await apiService.get(`/v1/mcp/tools/${encodeURIComponent(toolName)}`);
    return data;
  }

  /**
   * Get the input schema for a tool.
   * Endpoint: GET /v1/mcp/tools/{name}/schema
   */
  async getToolSchema(toolName: string): Promise<{
    name: string;
    inputSchema: MCPTool['inputSchema'];
  }> {
    const { data } = await apiService.get(`/v1/mcp/tools/${encodeURIComponent(toolName)}/schema`);
    return data;
  }

  /**
   * Get all unique tags from tools.
   * Endpoint: GET /v1/mcp/tools/tags
   */
  async getToolTags(): Promise<string[]> {
    const { data } = await apiService.get('/v1/mcp/tools/tags');
    return data.tags || [];
  }

  /**
   * Get all tool categories with counts.
   * Endpoint: GET /v1/mcp/tools/categories
   */
  async getToolCategories(): Promise<{ categories: Array<{ name: string; count: number }> }> {
    const { data } = await apiService.get('/v1/mcp/tools/categories');
    return data;
  }

  // ==========================================================================
  // Subscriptions (via Control-Plane-API - already uses this path)
  // ==========================================================================

  /**
   * Get user's MCP server subscriptions.
   * Endpoint: GET /v1/mcp/subscriptions
   */
  async getMySubscriptions(): Promise<ToolSubscription[]> {
    const { data } = await apiService.get('/v1/mcp/subscriptions');
    return data.items || [];
  }

  /**
   * Subscribe to an MCP server.
   * Endpoint: POST /v1/mcp/subscriptions
   */
  async subscribeTool(subscription: ToolSubscriptionCreate): Promise<ToolSubscription> {
    const { data } = await apiService.post('/v1/mcp/subscriptions', subscription);
    return data;
  }

  /**
   * Cancel a subscription.
   * Endpoint: DELETE /v1/mcp/subscriptions/{id}
   */
  async unsubscribeTool(subscriptionId: string): Promise<void> {
    await apiService.delete(`/v1/mcp/subscriptions/${subscriptionId}`);
  }

  /**
   * Update subscription settings.
   * Endpoint: PATCH /v1/mcp/subscriptions/{id}
   */
  async updateSubscription(
    subscriptionId: string,
    update: Partial<ToolSubscriptionCreate>
  ): Promise<ToolSubscription> {
    const { data } = await apiService.patch(`/v1/mcp/subscriptions/${subscriptionId}`, update);
    return data;
  }

  // ==========================================================================
  // Usage & Metrics
  // ==========================================================================

  /**
   * Get usage summary for the current user.
   * Endpoint: GET /v1/usage/me (from usage router)
   */
  async getMyUsage(params?: {
    period?: 'day' | 'week' | 'month';
    startDate?: string;
    endDate?: string;
  }): Promise<ToolUsageSummary> {
    const { data } = await apiService.get('/v1/usage/me', { params });
    return data;
  }

  /**
   * Get usage for a specific tool.
   */
  async getToolUsage(
    toolName: string,
    params?: {
      period?: 'day' | 'week' | 'month';
      startDate?: string;
      endDate?: string;
    }
  ): Promise<ToolUsageSummary> {
    const { data } = await apiService.get(`/v1/usage/tools/${encodeURIComponent(toolName)}`, { params });
    return data;
  }

  /**
   * Get usage history (time series data for charts).
   */
  async getUsageHistory(params?: {
    period?: 'day' | 'week' | 'month';
    groupBy?: 'hour' | 'day' | 'week';
    toolName?: string;
  }): Promise<{
    dataPoints: Array<{
      timestamp: string;
      calls: number;
      successRate: number;
      avgLatencyMs: number;
      costUnits: number;
    }>;
  }> {
    const { data } = await apiService.get('/v1/usage/history', { params });
    return data;
  }

  // ==========================================================================
  // Server Info
  // ==========================================================================

  /**
   * Get Control-Plane-API health.
   */
  async healthCheck(): Promise<{ status: 'healthy' | 'degraded' | 'unhealthy' }> {
    const { data } = await apiService.get('/health');
    return data;
  }

  // ==========================================================================
  // Legacy methods for backwards compatibility
  // These are no-ops since auth is handled by apiService
  // ==========================================================================

  setAuthToken(_token: string) {
    // No-op: auth token is managed by apiService
  }

  clearAuthToken() {
    // No-op: auth token is managed by apiService
  }
}

// Export singleton instance
export const mcpGatewayService = new MCPToolsService();
