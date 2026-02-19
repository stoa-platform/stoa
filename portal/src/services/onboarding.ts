/**
 * STOA Developer Portal - Onboarding Service (CAB-1325)
 *
 * API client for onboarding analytics endpoints (admin-only).
 */

import { apiClient } from './api';

// ============ Types ============

export interface FunnelStage {
  stage: string;
  count: number;
  conversion_rate: number | null;
}

export interface FunnelResponse {
  stages: FunnelStage[];
  total_started: number;
  total_completed: number;
  avg_ttftc_seconds: number | null;
  p50_ttftc_seconds: number | null;
  p90_ttftc_seconds: number | null;
}

export interface StalledUser {
  user_id: string;
  tenant_id: string;
  last_step: string | null;
  started_at: string;
  hours_stalled: number;
}

// ============ Service ============

export const onboardingService = {
  /**
   * Get onboarding funnel analytics
   * GET /v1/admin/onboarding/funnel
   */
  getFunnel: async (): Promise<FunnelResponse> => {
    const response = await apiClient.get<FunnelResponse>('/v1/admin/onboarding/funnel');
    return response.data;
  },

  /**
   * Get stalled users
   * GET /v1/admin/onboarding/stalled
   */
  getStalled: async (hours: number = 24): Promise<StalledUser[]> => {
    const response = await apiClient.get<StalledUser[]>('/v1/admin/onboarding/stalled', {
      params: { hours },
    });
    return response.data;
  },
};
