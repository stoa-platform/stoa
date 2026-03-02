/**
 * Tenant APIs Service
 *
 * API client for tenant-scoped API self-service (CAB-1634).
 * Endpoints: /v1/tenants/{tenant_id}/apis
 */

import { apiClient } from './api';

// ============ Types ============

export interface TenantAPI {
  id: string;
  tenant_id: string;
  name: string;
  display_name: string;
  version: string;
  description: string;
  backend_url: string;
  status: 'draft' | 'published' | 'deprecated';
  deployed_dev: boolean;
  deployed_staging: boolean;
  tags: string[];
  portal_promoted: boolean;
}

export interface TenantAPIListResponse {
  items: TenantAPI[];
  total: number;
  page: number;
  page_size: number;
}

export interface TenantAPICreatePayload {
  name: string;
  display_name: string;
  version?: string;
  description?: string;
  backend_url: string;
  openapi_spec?: string;
  tags?: string[];
}

export interface TenantAPIUpdatePayload {
  display_name?: string;
  version?: string;
  description?: string;
  backend_url?: string;
  openapi_spec?: string;
  tags?: string[];
}

// ============ Service ============

function basePath(tenantId: string) {
  return `/v1/tenants/${tenantId}/apis`;
}

export const tenantApisService = {
  async list(
    tenantId: string,
    params?: { page?: number; page_size?: number; environment?: string }
  ): Promise<TenantAPIListResponse> {
    const response = await apiClient.get<TenantAPIListResponse>(basePath(tenantId), {
      params,
    });
    return response.data;
  },

  async get(tenantId: string, apiId: string): Promise<TenantAPI> {
    const response = await apiClient.get<TenantAPI>(`${basePath(tenantId)}/${apiId}`);
    return response.data;
  },

  async create(tenantId: string, data: TenantAPICreatePayload): Promise<TenantAPI> {
    const response = await apiClient.post<TenantAPI>(basePath(tenantId), data);
    return response.data;
  },

  async update(tenantId: string, apiId: string, data: TenantAPIUpdatePayload): Promise<TenantAPI> {
    const response = await apiClient.put<TenantAPI>(`${basePath(tenantId)}/${apiId}`, data);
    return response.data;
  },

  async delete(tenantId: string, apiId: string): Promise<void> {
    await apiClient.delete(`${basePath(tenantId)}/${apiId}`);
  },
};

export default tenantApisService;
