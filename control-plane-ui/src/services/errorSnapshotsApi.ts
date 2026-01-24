/**
 * Error Snapshots API Service
 *
 * Service for interacting with MCP Gateway Error Snapshots API.
 *
 * Reference: CAB-397 - Error Snapshot / Flight Recorder (Time-Travel Debugging)
 */

import { config } from '../config';
import { apiService } from './api';
import type {
  MCPErrorSnapshot,
  MCPErrorSnapshotStats,
  MCPErrorSnapshotFilters,
  MCPErrorSnapshotListResponse,
  SnapshotResolutionStatus,
  SnapshotFiltersResponse,
} from '../types';

// MCP Gateway base URL
const MCP_GATEWAY_URL = config.services.mcpGateway.url;
const SNAPSHOTS_BASE = `${MCP_GATEWAY_URL}/mcp/v1/errors/snapshots`;

class ErrorSnapshotsService {
  /**
   * Get list of error snapshots with filters and pagination
   */
  async getSnapshots(
    filters?: MCPErrorSnapshotFilters,
    page: number = 1,
    pageSize: number = 20
  ): Promise<MCPErrorSnapshotListResponse> {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('page_size', String(pageSize));

    if (filters) {
      if (filters.error_types?.length) {
        filters.error_types.forEach((t) => params.append('error_type', t));
      }
      if (filters.status_codes?.length) {
        filters.status_codes.forEach((c) => params.append('status_code', String(c)));
      }
      if (filters.server_names?.length) {
        filters.server_names.forEach((s) => params.append('server_name', s));
      }
      if (filters.tool_names?.length) {
        filters.tool_names.forEach((t) => params.append('tool_name', t));
      }
      if (filters.resolution_status?.length) {
        filters.resolution_status.forEach((s) => params.append('resolution_status', s));
      }
      if (filters.start_date) params.set('start_date', filters.start_date);
      if (filters.end_date) params.set('end_date', filters.end_date);
      if (filters.min_cost_usd !== undefined) {
        params.set('min_cost_usd', String(filters.min_cost_usd));
      }
      if (filters.search) params.set('search', filters.search);
    }

    const { data } = await apiService.get<MCPErrorSnapshotListResponse>(
      `${SNAPSHOTS_BASE}?${params.toString()}`
    );
    return data;
  }

  /**
   * Get a single error snapshot by ID
   */
  async getSnapshot(snapshotId: string): Promise<MCPErrorSnapshot> {
    const { data } = await apiService.get<MCPErrorSnapshot>(
      `${SNAPSHOTS_BASE}/${snapshotId}`
    );
    return data;
  }

  /**
   * Get aggregated error statistics
   */
  async getStats(
    startDate?: string,
    endDate?: string
  ): Promise<MCPErrorSnapshotStats> {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);

    const queryString = params.toString();
    const url = queryString ? `${SNAPSHOTS_BASE}/stats?${queryString}` : `${SNAPSHOTS_BASE}/stats`;

    const { data } = await apiService.get<MCPErrorSnapshotStats>(url);
    return data;
  }

  /**
   * Get available filter values
   */
  async getFilters(): Promise<SnapshotFiltersResponse> {
    const { data } = await apiService.get<SnapshotFiltersResponse>(
      `${SNAPSHOTS_BASE}/filters`
    );
    return data;
  }

  /**
   * Update resolution status of a snapshot
   */
  async updateResolution(
    snapshotId: string,
    status: SnapshotResolutionStatus,
    notes?: string
  ): Promise<MCPErrorSnapshot> {
    const { data } = await apiService.patch<MCPErrorSnapshot>(
      `${SNAPSHOTS_BASE}/${snapshotId}`,
      {
        resolution_status: status,
        resolution_notes: notes,
      }
    );
    return data;
  }

  /**
   * Delete an error snapshot
   */
  async deleteSnapshot(snapshotId: string): Promise<void> {
    await apiService.delete(`${SNAPSHOTS_BASE}/${snapshotId}`);
  }

  /**
   * Generate cURL command to replay the request
   */
  async generateReplay(snapshotId: string): Promise<{ curl_command: string; warning?: string }> {
    const { data } = await apiService.post<{ curl_command: string; warning?: string }>(
      `${SNAPSHOTS_BASE}/${snapshotId}/replay`
    );
    return data;
  }
}

export const errorSnapshotsService = new ErrorSnapshotsService();
