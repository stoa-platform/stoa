/**
 * React Query hooks for onboarding progress (CAB-1325)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import {
  getProgress,
  markStep,
  complete,
  getTrialKey,
  type OnboardingProgressResponse,
  type OnboardingCompleteResponse,
  type TrialKeyInfo,
} from '../services/onboarding';

const ONBOARDING_KEY = ['onboarding', 'progress'];

export function useOnboardingProgress() {
  const { isAuthenticated, accessToken, user } = useAuth();

  return useQuery<OnboardingProgressResponse>({
    queryKey: ONBOARDING_KEY,
    queryFn: getProgress,
    enabled: isAuthenticated && !!accessToken && !!user?.tenant_id,
    staleTime: 60_000,
  });
}

export function useMarkStep() {
  const queryClient = useQueryClient();

  return useMutation<OnboardingProgressResponse, Error, string>({
    mutationFn: (stepName: string) => markStep(stepName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ONBOARDING_KEY });
    },
  });
}

export function useCompleteOnboarding() {
  const queryClient = useQueryClient();

  return useMutation<OnboardingCompleteResponse, Error, void>({
    mutationFn: () => complete(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ONBOARDING_KEY });
    },
  });
}

export function useTrialKey() {
  const { isAuthenticated, accessToken, user } = useAuth();

  return useQuery<TrialKeyInfo>({
    queryKey: ['onboarding', 'trial-key'],
    queryFn: getTrialKey,
    enabled: isAuthenticated && !!accessToken && !!user?.tenant_id,
    staleTime: 5 * 60_000,
  });
}
