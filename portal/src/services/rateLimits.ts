/**
 * Rate Limits Dashboard Service (CAB-1470)
 */

import { apiClient } from './api';
import type { RateLimitsResponse } from '../types';

async function getRateLimits(): Promise<RateLimitsResponse> {
  try {
    const response = await apiClient.get<RateLimitsResponse>('/v1/portal/rate-limits');
    return response.data;
  } catch {
    console.warn('Rate limits endpoint not available, using fallback');
    return { rate_limits: [], total: 0 };
  }
}

export const rateLimitsService = {
  getRateLimits,
};
