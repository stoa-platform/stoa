/**
 * STOA Developer Portal - MCP Tools Service
 *
 * API service for MCP Tools catalog and subscriptions.
 */

import { apiClient } from './api';
import type { MCPTool, Subscription, PaginatedResponse } from '../types';

export interface ListToolsParams {
  page?: number;
  pageSize?: number;
  category?: string;
  search?: string;
  status?: 'active' | 'deprecated' | 'beta';
}

export interface SubscribeToToolRequest {
  toolId: string;
  plan: 'free' | 'basic' | 'premium';
}

/**
 * MCP Tools service
 */
export const toolsService = {
  /**
   * List all available MCP tools
   */
  async listTools(params?: ListToolsParams): Promise<PaginatedResponse<MCPTool>> {
    const response = await apiClient.get<PaginatedResponse<MCPTool>>('/v1/tools', { params });
    return response.data;
  },

  /**
   * Get a single tool by ID
   */
  async getTool(id: string): Promise<MCPTool> {
    const response = await apiClient.get<MCPTool>(`/v1/tools/${id}`);
    return response.data;
  },

  /**
   * Get tools by category
   */
  async getByCategory(category: string): Promise<MCPTool[]> {
    const response = await apiClient.get<PaginatedResponse<MCPTool>>('/v1/tools', {
      params: { category, pageSize: 100 },
    });
    return response.data.items;
  },

  /**
   * Get all available categories
   */
  async getCategories(): Promise<string[]> {
    const response = await apiClient.get<{ categories: string[] }>('/v1/tools/categories');
    return response.data.categories;
  },

  /**
   * Subscribe to a tool
   */
  async subscribe(data: SubscribeToToolRequest): Promise<Subscription> {
    const response = await apiClient.post<Subscription>('/v1/tools/subscriptions', data);
    return response.data;
  },

  /**
   * Get user's tool subscriptions
   */
  async getSubscriptions(): Promise<PaginatedResponse<Subscription>> {
    const response = await apiClient.get<PaginatedResponse<Subscription>>('/v1/tools/subscriptions');
    return response.data;
  },

  /**
   * Get a single tool subscription
   */
  async getSubscription(id: string): Promise<Subscription> {
    const response = await apiClient.get<Subscription>(`/v1/tools/subscriptions/${id}`);
    return response.data;
  },

  /**
   * Cancel a tool subscription
   */
  async cancelSubscription(id: string): Promise<void> {
    await apiClient.delete(`/v1/tools/subscriptions/${id}`);
  },

  /**
   * Get tool input schema
   */
  async getInputSchema(id: string): Promise<object> {
    const response = await apiClient.get<object>(`/v1/tools/${id}/schema`);
    return response.data;
  },
};
