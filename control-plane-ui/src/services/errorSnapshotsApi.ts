/**
 * Error Snapshots API Service
 *
 * Routes through the CP API (/v1/snapshots) via same-origin nginx proxy.
 * No cross-origin calls — avoids CORS issues with the gateway.
 *
 * Reference: CAB-397 - Error Snapshot / Flight Recorder (Time-Travel Debugging)
 */

import { apiService } from './api';
import type {
  ErrorSnapshotDetail,
  ErrorSnapshotStats,
  ErrorSnapshotFilters,
  ErrorSnapshotListResponse,
  SnapshotResolutionStatus,
  SnapshotFiltersResponse,
} from '../types';

class ErrorSnapshotsService {
  /**
   * Get list of error snapshots with filters and pagination
   */
  async getSnapshots(
    filters?: ErrorSnapshotFilters,
    page: number = 1,
    pageSize: number = 20
  ): Promise<ErrorSnapshotListResponse> {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('page_size', String(pageSize));

    if (filters) {
      if (filters.trigger) params.set('trigger', filters.trigger);
      if (filters.status_code) params.set('status_code', String(filters.status_code));
      if (filters.source) params.set('source', filters.source);
      if (filters.resolution_status) params.set('resolution_status', filters.resolution_status);
      if (filters.start_date) params.set('start_date', filters.start_date);
      if (filters.end_date) params.set('end_date', filters.end_date);
      if (filters.path_contains) params.set('path_contains', filters.path_contains);
    }

    const { data } = await apiService.get<ErrorSnapshotListResponse>(
      `/v1/snapshots?${params.toString()}`
    );
    return data;
  }

  /**
   * Get a single error snapshot by ID
   */
  async getSnapshot(snapshotId: string): Promise<ErrorSnapshotDetail> {
    const { data } = await apiService.get<ErrorSnapshotDetail>(`/v1/snapshots/${snapshotId}`);
    return data;
  }

  /**
   * Get aggregated error statistics
   */
  async getStats(startDate?: string, endDate?: string): Promise<ErrorSnapshotStats> {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);

    const queryString = params.toString();
    const url = queryString ? `/v1/snapshots/stats?${queryString}` : '/v1/snapshots/stats';

    const { data } = await apiService.get<ErrorSnapshotStats>(url);
    return data;
  }

  /**
   * Get available filter values
   */
  async getFilters(): Promise<SnapshotFiltersResponse> {
    const { data } = await apiService.get<SnapshotFiltersResponse>('/v1/snapshots/filters');
    return data;
  }

  /**
   * Update resolution status of a snapshot
   */
  async updateResolution(
    snapshotId: string,
    status: SnapshotResolutionStatus,
    notes?: string
  ): Promise<ErrorSnapshotDetail> {
    const { data } = await apiService.patch<ErrorSnapshotDetail>(`/v1/snapshots/${snapshotId}`, {
      resolution_status: status,
      resolution_notes: notes,
    });
    return data;
  }

  /**
   * Delete an error snapshot
   */
  async deleteSnapshot(snapshotId: string): Promise<void> {
    await apiService.delete(`/v1/snapshots/${snapshotId}`);
  }

  /**
   * Generate cURL command to replay the request
   */
  async generateReplay(snapshotId: string): Promise<{ curl_command: string; warning?: string }> {
    const { data } = await apiService.post<{ curl_command: string; warning?: string }>(
      `/v1/snapshots/${snapshotId}/replay`
    );
    return data;
  }
}

export const errorSnapshotsService = new ErrorSnapshotsService();
