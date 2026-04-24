import { httpClient, path } from '../http';
import type {
  AdminUserListResponse,
  AccessRequestListResponse,
  PlatformSettingsResponse,
  PlatformSetting,
  RoleListResponse,
  ProspectListResponse,
  ProspectsMetricsResponse,
  ProspectDetail,
} from '../../types';

export const adminClient = {
  // Users (CAB-1454)
  async listUsers(params: {
    role?: string;
    status?: string;
    search?: string;
    page?: number;
    limit?: number;
  }): Promise<AdminUserListResponse> {
    const { data } = await httpClient.get('/v1/admin/users', { params });
    return data;
  },

  // Platform Settings (CAB-1454)
  async listSettings(params?: { category?: string }): Promise<PlatformSettingsResponse> {
    const { data } = await httpClient.get('/v1/admin/settings', { params });
    return data;
  },

  async updateSetting(key: string, value: string): Promise<PlatformSetting> {
    const { data } = await httpClient.put(path('v1', 'admin', 'settings', key), { value });
    return data;
  },

  // RBAC Roles (CAB-1454)
  async listRoles(): Promise<RoleListResponse> {
    const { data } = await httpClient.get('/v1/admin/roles');
    return data;
  },

  // Access Requests (CAB-1468)
  async listAccessRequests(params: {
    status?: string;
    page?: number;
    limit?: number;
  }): Promise<AccessRequestListResponse> {
    const { data } = await httpClient.get('/v1/admin/access-requests', { params });
    return data;
  },

  // Prospects (CAB-911)
  async listProspects(params: {
    company?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    limit?: number;
  }): Promise<ProspectListResponse> {
    const { data } = await httpClient.get('/v1/admin/prospects', { params });
    return data;
  },

  async getProspectsMetrics(params?: {
    date_from?: string;
    date_to?: string;
  }): Promise<ProspectsMetricsResponse> {
    const { data } = await httpClient.get('/v1/admin/prospects/metrics', { params });
    return data;
  },

  async getProspect(inviteId: string): Promise<ProspectDetail> {
    const { data } = await httpClient.get(path('v1', 'admin', 'prospects', inviteId));
    return data;
  },

  async exportProspectsCSV(params?: {
    company?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<Blob> {
    const { data } = await httpClient.get('/v1/admin/prospects/export', {
      params,
      responseType: 'blob',
    });
    return data;
  },
};
