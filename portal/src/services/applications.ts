/**
 * STOA Developer Portal - Applications Service
 *
 * Service for managing consumer applications (OAuth clients).
 */

import { apiClient } from './api';
import type { Application, ApplicationCreateRequest, PaginatedResponse } from '../types';

export interface ListApplicationsParams {
  page?: number;
  pageSize?: number;
  status?: 'active' | 'suspended';
}

export const applicationsService = {
  /**
   * List user's applications
   */
  listApplications: async (params?: ListApplicationsParams): Promise<PaginatedResponse<Application>> => {
    const response = await apiClient.get<PaginatedResponse<Application>>('/v1/applications', {
      params: {
        page: params?.page || 1,
        page_size: params?.pageSize || 20,
        status: params?.status,
      },
    });
    return response.data;
  },

  /**
   * Get a single application by ID
   */
  getApplication: async (id: string): Promise<Application> => {
    const response = await apiClient.get<Application>(`/v1/applications/${id}`);
    return response.data;
  },

  /**
   * Create a new application
   * Returns the application with client_secret (only shown once!)
   */
  createApplication: async (data: ApplicationCreateRequest): Promise<Application> => {
    const response = await apiClient.post<Application>('/v1/applications', data);
    return response.data;
  },

  /**
   * Update an application
   */
  updateApplication: async (id: string, data: Partial<ApplicationCreateRequest>): Promise<Application> => {
    const response = await apiClient.patch<Application>(`/v1/applications/${id}`, data);
    return response.data;
  },

  /**
   * Delete an application
   */
  deleteApplication: async (id: string): Promise<void> => {
    await apiClient.delete(`/v1/applications/${id}`);
  },

  /**
   * Regenerate client secret
   * Returns the new client_secret (only shown once!)
   */
  regenerateSecret: async (id: string): Promise<{ clientSecret: string }> => {
    const response = await apiClient.post<{ clientSecret: string }>(
      `/v1/applications/${id}/regenerate-secret`
    );
    return response.data;
  },
};

export default applicationsService;
