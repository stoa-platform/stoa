/**
 * Onboarding service — API calls for zero-touch trial (CAB-1325)
 */

import { apiClient } from './api';

export interface OnboardingProgressResponse {
  tenant_id: string;
  user_id: string;
  steps_completed: Record<string, string>;
  started_at: string;
  completed_at: string | null;
  ttftc_seconds: number | null;
  is_complete: boolean;
}

export interface OnboardingCompleteResponse {
  completed: boolean;
  ttftc_seconds: number | null;
}

export interface TrialKeyInfo {
  key_prefix: string;
  name: string;
  rate_limit_rpm: number;
  expires_at: string | null;
  status: string;
  created_at: string;
}

export async function getProgress(): Promise<OnboardingProgressResponse> {
  const response = await apiClient.get<OnboardingProgressResponse>('/v1/me/onboarding');
  return response.data;
}

export async function markStep(stepName: string): Promise<OnboardingProgressResponse> {
  const response = await apiClient.put<OnboardingProgressResponse>(
    `/v1/me/onboarding/steps/${stepName}`
  );
  return response.data;
}

export async function complete(): Promise<OnboardingCompleteResponse> {
  const response = await apiClient.post<OnboardingCompleteResponse>('/v1/me/onboarding/complete');
  return response.data;
}

export async function getTrialKey(): Promise<TrialKeyInfo> {
  const response = await apiClient.get<TrialKeyInfo>('/v1/me/onboarding/trial-key');
  return response.data;
}
