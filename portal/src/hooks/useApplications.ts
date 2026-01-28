// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * STOA Developer Portal - Application Hooks
 *
 * React Query hooks for consumer application operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { applicationsService, ListApplicationsParams } from '../services/applications';
import type { Application, ApplicationCreateRequest, PaginatedResponse } from '../types';

/**
 * Hook to list user's applications
 */
export function useApplications(params?: ListApplicationsParams) {
  return useQuery<PaginatedResponse<Application>>({
    queryKey: ['applications', params],
    queryFn: () => applicationsService.listApplications(params),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a single application by ID
 */
export function useApplication(id: string | undefined) {
  return useQuery<Application>({
    queryKey: ['application', id],
    queryFn: () => applicationsService.getApplication(id!),
    enabled: !!id,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to create a new application
 */
export function useCreateApplication() {
  const queryClient = useQueryClient();

  return useMutation<Application, Error, ApplicationCreateRequest>({
    mutationFn: (data) => applicationsService.createApplication(data),
    onSuccess: () => {
      // Invalidate applications list
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

/**
 * Hook to update an application
 */
export function useUpdateApplication(id: string) {
  const queryClient = useQueryClient();

  return useMutation<Application, Error, Partial<ApplicationCreateRequest>>({
    mutationFn: (data) => applicationsService.updateApplication(id, data),
    onSuccess: () => {
      // Invalidate both the list and the specific application
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['application', id] });
    },
  });
}

/**
 * Hook to delete an application
 */
export function useDeleteApplication() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (id) => applicationsService.deleteApplication(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

/**
 * Hook to regenerate client secret
 */
export function useRegenerateSecret(id: string) {
  const queryClient = useQueryClient();

  return useMutation<{ clientSecret: string }, Error>({
    mutationFn: () => applicationsService.regenerateSecret(id),
    onSuccess: () => {
      // Invalidate the specific application to refresh data
      queryClient.invalidateQueries({ queryKey: ['application', id] });
    },
  });
}
