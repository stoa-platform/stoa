/**
 * Tests for Usage Service (CAB-280)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { formatLatency, getStatusColor, usageService } from './usage';

// Mock the api module
vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;

describe('usage service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('formatLatency', () => {
    it('should format milliseconds for values under 1000', () => {
      expect(formatLatency(50)).toBe('50ms');
      expect(formatLatency(999)).toBe('999ms');
    });

    it('should format seconds for values 1000+', () => {
      expect(formatLatency(1000)).toBe('1.00s');
      expect(formatLatency(1500)).toBe('1.50s');
      expect(formatLatency(2345)).toBe('2.35s');
    });
  });

  describe('getStatusColor', () => {
    it('should return emerald for success', () => {
      expect(getStatusColor('success')).toBe('emerald');
    });

    it('should return red for error', () => {
      expect(getStatusColor('error')).toBe('red');
    });

    it('should return amber for timeout', () => {
      expect(getStatusColor('timeout')).toBe('amber');
    });

    it('should return gray for unknown status', () => {
      expect(getStatusColor('unknown')).toBe('gray');
    });
  });

  describe('usageService.getSummary', () => {
    it('should call GET /v1/usage/me', async () => {
      const mockData = { this_week: { total_calls: 100 } };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await usageService.getSummary();

      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me');
      expect(result).toEqual(mockData);
    });
  });

  describe('usageService.getCalls', () => {
    it('should call GET /v1/usage/me/calls with default params', async () => {
      const mockData = { calls: [], total: 0 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await usageService.getCalls();

      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me/calls', {
        params: {
          limit: 20,
          offset: 0,
          status: undefined,
          tool_id: undefined,
          from_date: undefined,
          to_date: undefined,
        },
      });
      expect(result).toEqual(mockData);
    });

    it('should pass custom params', async () => {
      const mockData = { calls: [], total: 0 };
      mockGet.mockResolvedValueOnce({ data: mockData });

      await usageService.getCalls({
        limit: 10,
        offset: 5,
        status: 'error',
        tool_id: 'tool-1',
      });

      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me/calls', {
        params: expect.objectContaining({
          limit: 10,
          offset: 5,
          status: 'error',
          tool_id: 'tool-1',
        }),
      });
    });
  });

  describe('usageService.getActiveSubscriptions', () => {
    it('should call GET /v1/usage/me/subscriptions', async () => {
      const mockSubs = [{ id: 'sub-1', status: 'active' }];
      mockGet.mockResolvedValueOnce({ data: mockSubs });

      const result = await usageService.getActiveSubscriptions();

      expect(mockGet).toHaveBeenCalledWith('/v1/usage/me/subscriptions');
      expect(result).toEqual(mockSubs);
    });
  });
});
