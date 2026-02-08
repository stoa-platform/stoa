/**
 * Tests for Dashboard Service (CAB-299)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { dashboardService } from './dashboard';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

vi.mock('./mcpClient', () => ({
  mcpClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from './api';
import { mcpClient } from './mcpClient';

const mockApiGet = apiClient.get as Mock;
const mockMcpGet = mcpClient.get as Mock;

describe('dashboardService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getStats', () => {
    it('should return stats from /v1/dashboard/stats', async () => {
      const mockStats = {
        tools_available: 10,
        active_subscriptions: 5,
        api_calls_this_week: 1234,
      };
      mockApiGet.mockResolvedValueOnce({ data: mockStats });

      const result = await dashboardService.getStats();

      expect(mockApiGet).toHaveBeenCalledWith('/v1/dashboard/stats');
      expect(result).toEqual(mockStats);
    });

    it('should fall back to aggregated stats on error', async () => {
      // Main endpoint fails
      mockApiGet.mockRejectedValueOnce(new Error('Not found'));

      // Fallback calls
      mockMcpGet.mockResolvedValueOnce({
        data: { tools: [{ id: 't1' }, { id: 't2' }] },
      }); // tools
      mockMcpGet.mockResolvedValueOnce({
        data: {
          subscriptions: [{ status: 'active' }, { status: 'active' }, { status: 'revoked' }],
        },
      }); // subscriptions
      mockApiGet.mockResolvedValueOnce({
        data: { this_week: { total_calls: 42 } },
      }); // usage

      const result = await dashboardService.getStats();

      expect(result.tools_available).toBe(2);
      expect(result.active_subscriptions).toBe(2);
      expect(result.api_calls_this_week).toBe(42);
    });

    it('should handle partial fallback failures gracefully', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Not found'));

      // All fallback requests fail
      mockMcpGet.mockRejectedValueOnce(new Error('Network'));
      mockMcpGet.mockRejectedValueOnce(new Error('Network'));
      mockApiGet.mockRejectedValueOnce(new Error('Network'));

      const result = await dashboardService.getStats();

      expect(result.tools_available).toBe(0);
      expect(result.active_subscriptions).toBe(0);
      expect(result.api_calls_this_week).toBe(0);
    });
  });

  describe('getRecentActivity', () => {
    it('should return activity from /v1/dashboard/activity', async () => {
      const mockActivity = {
        activity: [
          { id: 'a1', type: 'api.call', title: 'Call 1', timestamp: '2026-02-07T10:00:00Z' },
        ],
      };
      mockApiGet.mockResolvedValueOnce({ data: mockActivity });

      const result = await dashboardService.getRecentActivity();

      expect(mockApiGet).toHaveBeenCalledWith('/v1/dashboard/activity', { params: { limit: 5 } });
      expect(result).toHaveLength(1);
    });

    it('should accept custom limit', async () => {
      mockApiGet.mockResolvedValueOnce({ data: { activity: [] } });

      await dashboardService.getRecentActivity(10);

      expect(mockApiGet).toHaveBeenCalledWith('/v1/dashboard/activity', { params: { limit: 10 } });
    });

    it('should fall back to usage calls on error', async () => {
      // Main endpoint fails
      mockApiGet.mockRejectedValueOnce(new Error('Not found'));
      // Fallback: usage calls
      mockApiGet.mockResolvedValueOnce({
        data: {
          calls: [
            {
              id: 'c1',
              tool_id: 'tool-1',
              tool_name: 'My Tool',
              timestamp: '2026-02-07T10:00:00Z',
              status: 'success',
              latency_ms: 150,
            },
          ],
        },
      });

      const result = await dashboardService.getRecentActivity();

      expect(result).toHaveLength(1);
      expect(result[0].type).toBe('api.call');
      expect(result[0].title).toContain('My Tool');
    });

    it('should return empty array when both endpoints fail', async () => {
      mockApiGet.mockRejectedValueOnce(new Error('Not found'));
      mockApiGet.mockRejectedValueOnce(new Error('Not found'));

      const result = await dashboardService.getRecentActivity();

      expect(result).toEqual([]);
    });
  });

  describe('getDashboard', () => {
    it('should aggregate stats and activity', async () => {
      const mockStats = {
        tools_available: 3,
        active_subscriptions: 1,
        api_calls_this_week: 100,
      };
      const mockActivity = {
        activity: [
          { id: 'a1', type: 'api.call', title: 'Call', timestamp: '2026-02-07T10:00:00Z' },
        ],
      };
      // getStats call
      mockApiGet.mockResolvedValueOnce({ data: mockStats });
      // getRecentActivity call
      mockApiGet.mockResolvedValueOnce({ data: mockActivity });

      const result = await dashboardService.getDashboard();

      expect(result.stats).toEqual(mockStats);
      expect(result.recent_activity).toHaveLength(1);
    });
  });
});
