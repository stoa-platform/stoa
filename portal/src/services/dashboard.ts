// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * STOA Developer Portal - Dashboard Service (CAB-299)
 *
 * Aggregates stats from multiple sources for the home dashboard.
 */

import { apiClient } from './api';
import { mcpClient } from './mcpClient';
import type { DashboardStats, DashboardData, RecentActivityItem } from '../types';

/**
 * Fetch dashboard stats from backend
 * GET /v1/dashboard/stats
 */
async function getStats(): Promise<DashboardStats> {
  try {
    const response = await apiClient.get<DashboardStats>('/v1/dashboard/stats');
    return response.data;
  } catch (error) {
    // Fallback: aggregate from existing endpoints
    console.warn('Dashboard stats endpoint not available, using fallback');
    return getFallbackStats();
  }
}

/**
 * Fallback: aggregate stats from existing endpoints
 */
async function getFallbackStats(): Promise<DashboardStats> {
  const [toolsResponse, subscriptionsResponse, usageResponse] = await Promise.allSettled([
    mcpClient.get('/tools'),
    mcpClient.get('/subscriptions'),
    apiClient.get('/v1/usage/me'),
  ]);

  // Extract tools count
  let toolsAvailable = 0;
  if (toolsResponse.status === 'fulfilled') {
    const data = toolsResponse.value.data;
    toolsAvailable = data?.tools?.length || data?.total_count || 0;
  }

  // Extract subscriptions count
  let activeSubscriptions = 0;
  if (subscriptionsResponse.status === 'fulfilled') {
    const data = subscriptionsResponse.value.data;
    const subs = data?.subscriptions || [];
    activeSubscriptions = subs.filter((s: { status: string }) => s.status === 'active').length;
  }

  // Extract API calls this week
  let apiCallsThisWeek = 0;
  if (usageResponse.status === 'fulfilled') {
    const data = usageResponse.value.data;
    apiCallsThisWeek = data?.this_week?.total_calls || 0;
  }

  return {
    tools_available: toolsAvailable,
    active_subscriptions: activeSubscriptions,
    api_calls_this_week: apiCallsThisWeek,
  };
}

/**
 * Fetch recent activity
 * GET /v1/dashboard/activity
 */
async function getRecentActivity(limit: number = 5): Promise<RecentActivityItem[]> {
  try {
    const response = await apiClient.get<{ activity: RecentActivityItem[] }>(
      '/v1/dashboard/activity',
      { params: { limit } }
    );
    return response.data.activity;
  } catch (error) {
    // Fallback: use recent calls from usage API
    console.warn('Dashboard activity endpoint not available, using fallback');
    return getFallbackActivity(limit);
  }
}

/**
 * Fallback: derive activity from recent calls
 */
async function getFallbackActivity(limit: number): Promise<RecentActivityItem[]> {
  try {
    const response = await apiClient.get('/v1/usage/me/calls', { params: { limit } });
    const calls = response.data?.calls || [];

    return calls.map((call: {
      id: string;
      tool_id: string;
      tool_name?: string;
      timestamp: string;
      status: string;
      latency_ms?: number;
    }) => ({
      id: call.id,
      type: 'api.call' as const,
      title: `API call to ${call.tool_name || call.tool_id}`,
      description: call.status === 'success'
        ? `Completed in ${call.latency_ms}ms`
        : `Failed: ${call.status}`,
      tool_id: call.tool_id,
      tool_name: call.tool_name,
      timestamp: call.timestamp,
    }));
  } catch {
    return [];
  }
}

/**
 * Fetch complete dashboard data
 */
async function getDashboard(): Promise<DashboardData> {
  const [stats, activity] = await Promise.all([
    getStats(),
    getRecentActivity(),
  ]);

  return {
    stats,
    recent_activity: activity,
  };
}

export const dashboardService = {
  getStats,
  getRecentActivity,
  getDashboard,
};

export default dashboardService;
