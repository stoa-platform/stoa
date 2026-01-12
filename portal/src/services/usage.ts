/**
 * STOA Developer Portal - Usage Dashboard Service (CAB-280)
 *
 * API client for usage statistics endpoints.
 * Uses Control-Plane API via Gateway.
 */

import { apiClient } from './api';
import type {
  UsageSummary,
  UsageCallsResponse,
  UsageCallsParams,
  ActiveSubscription,
} from '../types';

// ============ Helper Functions ============

/**
 * Format latency in human-readable form
 */
export function formatLatency(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }
  return `${(ms / 1000).toFixed(2)}s`;
}

/**
 * Get color class for status badge
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case 'success':
      return 'emerald';
    case 'error':
      return 'red';
    case 'timeout':
      return 'amber';
    default:
      return 'gray';
  }
}

// ============ Service ============

export const usageService = {
  /**
   * Get usage summary for current user
   * GET /v1/usage/me
   */
  getSummary: async (): Promise<UsageSummary> => {
    const response = await apiClient.get<UsageSummary>('/v1/usage/me');
    return response.data;
  },

  /**
   * Get recent calls for current user
   * GET /v1/usage/me/calls
   */
  getCalls: async (params?: UsageCallsParams): Promise<UsageCallsResponse> => {
    const response = await apiClient.get<UsageCallsResponse>('/v1/usage/me/calls', {
      params: {
        limit: params?.limit || 20,
        offset: params?.offset || 0,
        status: params?.status,
        tool_id: params?.tool_id,
        from_date: params?.from_date,
        to_date: params?.to_date,
      },
    });
    return response.data;
  },

  /**
   * Get active subscriptions for current user
   * GET /v1/usage/me/subscriptions
   */
  getActiveSubscriptions: async (): Promise<ActiveSubscription[]> => {
    const response = await apiClient.get<ActiveSubscription[]>('/v1/usage/me/subscriptions');
    return response.data;
  },
};

export default usageService;
