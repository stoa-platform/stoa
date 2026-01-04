import axios, { AxiosInstance } from 'axios';
import { config } from '../config';
import type {
  MCPTool,
  ListToolsResponse,
  ToolUsageSummary,
  ToolSubscription,
  ToolSubscriptionCreate,
} from '../types';

const MCP_GATEWAY_URL = config.services.mcpGateway.url;

/**
 * MCP Gateway API Service
 *
 * Client for interacting with the STOA MCP Gateway.
 * Provides access to AI tools catalog, subscriptions, and usage metrics.
 */
class MCPGatewayService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: MCP_GATEWAY_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  setAuthToken(token: string) {
    this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  clearAuthToken() {
    delete this.client.defaults.headers.common['Authorization'];
  }

  // ==========================================================================
  // Tools Catalog
  // ==========================================================================

  /**
   * List all available tools with optional filtering.
   */
  async getTools(params?: {
    tenant?: string;
    tag?: string;
    search?: string;
    cursor?: string;
    limit?: number;
  }): Promise<ListToolsResponse> {
    const { data } = await this.client.get('/mcp/tools', {
      params: {
        tenant: params?.tenant,
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
   */
  async getTool(toolName: string): Promise<MCPTool> {
    const { data } = await this.client.get(`/mcp/tools/${toolName}`);
    return data;
  }

  /**
   * Get the input schema for a tool.
   */
  async getToolSchema(toolName: string): Promise<{
    name: string;
    inputSchema: MCPTool['inputSchema'];
  }> {
    const { data } = await this.client.get(`/mcp/tools/${toolName}/schema`);
    return data;
  }

  /**
   * Get all unique tags from tools.
   */
  async getToolTags(): Promise<string[]> {
    const { data } = await this.client.get('/mcp/tools/tags');
    return data.tags || [];
  }

  // ==========================================================================
  // Subscriptions
  // ==========================================================================

  /**
   * Get user's tool subscriptions.
   */
  async getMySubscriptions(): Promise<ToolSubscription[]> {
    const { data } = await this.client.get('/mcp/subscriptions');
    return data.subscriptions || [];
  }

  /**
   * Subscribe to a tool.
   */
  async subscribeTool(subscription: ToolSubscriptionCreate): Promise<ToolSubscription> {
    const { data } = await this.client.post('/mcp/subscriptions', subscription);
    return data;
  }

  /**
   * Unsubscribe from a tool.
   */
  async unsubscribeTool(subscriptionId: string): Promise<void> {
    await this.client.delete(`/mcp/subscriptions/${subscriptionId}`);
  }

  /**
   * Update subscription settings.
   */
  async updateSubscription(
    subscriptionId: string,
    update: Partial<ToolSubscriptionCreate>
  ): Promise<ToolSubscription> {
    const { data } = await this.client.patch(`/mcp/subscriptions/${subscriptionId}`, update);
    return data;
  }

  // ==========================================================================
  // Usage & Metrics
  // ==========================================================================

  /**
   * Get usage summary for the current user.
   */
  async getMyUsage(params?: {
    period?: 'day' | 'week' | 'month';
    startDate?: string;
    endDate?: string;
  }): Promise<ToolUsageSummary> {
    const { data } = await this.client.get('/mcp/usage/me', { params });
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
    const { data } = await this.client.get(`/mcp/usage/tools/${toolName}`, { params });
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
    const { data } = await this.client.get('/mcp/usage/history', { params });
    return data;
  }

  // ==========================================================================
  // Server Info
  // ==========================================================================

  /**
   * Get MCP server information.
   */
  async getServerInfo(): Promise<{
    name: string;
    version: string;
    protocolVersion: string;
    capabilities: {
      tools: boolean;
      resources: boolean;
      prompts: boolean;
    };
  }> {
    const { data } = await this.client.get('/mcp/server-info');
    return data;
  }

  /**
   * Health check.
   */
  async healthCheck(): Promise<{ status: 'healthy' | 'degraded' | 'unhealthy' }> {
    const { data } = await this.client.get('/health');
    return data;
  }
}

export const mcpGatewayService = new MCPGatewayService();
