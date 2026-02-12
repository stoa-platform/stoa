/**
 * STOA Developer Portal - Error Snapshots Service
 *
 * Service for browsing and managing error snapshots (time-travel debugging).
 * Uses /v1/snapshots endpoints.
 */

import { apiClient } from './api';
import type {
  ErrorSnapshot,
  SnapshotSummary,
  SnapshotListResponse,
  SnapshotFiltersResponse,
  ReplayResponse,
  ResolutionStatus,
} from '../types';

export interface ListSnapshotsParams {
  page?: number;
  pageSize?: number;
  trigger?: string;
  source?: string;
  status_code?: number;
  resolution?: string;
  path?: string;
}

export const errorSnapshotsService = {
  listSnapshots: async (params?: ListSnapshotsParams): Promise<SnapshotListResponse> => {
    try {
      const response = await apiClient.get<SnapshotListResponse>('/v1/snapshots', {
        params: {
          page: params?.page || 1,
          page_size: params?.pageSize || 20,
          trigger: params?.trigger,
          source: params?.source,
          status_code: params?.status_code,
          resolution: params?.resolution,
          path: params?.path,
        },
      });
      return response.data;
    } catch (error) {
      console.error('Failed to fetch snapshots:', error);
      return { items: [], total: 0, page: 1, page_size: 20 };
    }
  },

  getSnapshot: async (id: string): Promise<ErrorSnapshot | null> => {
    try {
      const response = await apiClient.get<ErrorSnapshot>(`/v1/snapshots/${id}`);
      return response.data;
    } catch (error) {
      console.error(`Failed to fetch snapshot ${id}:`, error);
      return null;
    }
  },

  getStats: async (): Promise<SnapshotSummary | null> => {
    try {
      const response = await apiClient.get<SnapshotSummary>('/v1/snapshots/stats');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch snapshot stats:', error);
      return null;
    }
  },

  getFilters: async (): Promise<SnapshotFiltersResponse | null> => {
    try {
      const response = await apiClient.get<SnapshotFiltersResponse>('/v1/snapshots/filters');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch snapshot filters:', error);
      return null;
    }
  },

  updateResolution: async (
    id: string,
    resolution: ResolutionStatus,
    notes?: string
  ): Promise<boolean> => {
    try {
      await apiClient.patch(`/v1/snapshots/${id}`, { resolution, resolution_notes: notes });
      return true;
    } catch (error) {
      console.error(`Failed to update snapshot ${id} resolution:`, error);
      return false;
    }
  },

  generateReplay: async (id: string): Promise<ReplayResponse | null> => {
    try {
      const response = await apiClient.post<ReplayResponse>(`/v1/snapshots/${id}/replay`);
      return response.data;
    } catch (error) {
      console.error(`Failed to generate replay for snapshot ${id}:`, error);
      return null;
    }
  },
};

export default errorSnapshotsService;
