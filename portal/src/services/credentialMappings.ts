/**
 * Credential Mappings API Service (CAB-1432)
 *
 * API client for consumer→API backend credential mappings.
 * Endpoints: /v1/tenants/{tenant_id}/credential-mappings
 */

import { apiClient } from './api';

// ============ Types ============

export type CredentialAuthType = 'api_key' | 'bearer' | 'basic';

export interface CredentialMapping {
  id: string;
  consumer_id: string;
  api_id: string;
  tenant_id: string;
  auth_type: CredentialAuthType;
  header_name: string;
  has_credential: boolean;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface CredentialMappingListResponse {
  items: CredentialMapping[];
  total: number;
  page: number;
  page_size: number;
}

export interface CredentialMappingCreate {
  consumer_id: string;
  api_id: string;
  auth_type: CredentialAuthType;
  header_name: string;
  credential_value: string;
  description?: string;
}

export interface CredentialMappingUpdate {
  auth_type?: CredentialAuthType;
  header_name?: string;
  credential_value?: string;
  description?: string;
  is_active?: boolean;
}

// ============ Service ============

function basePath(tenantId: string) {
  return `/v1/tenants/${tenantId}/credential-mappings`;
}

export const credentialMappingsService = {
  async list(
    tenantId: string,
    params?: { consumer_id?: string; api_id?: string; page?: number; page_size?: number }
  ): Promise<CredentialMappingListResponse> {
    const response = await apiClient.get<CredentialMappingListResponse>(basePath(tenantId), {
      params,
    });
    return response.data;
  },

  async get(tenantId: string, id: string): Promise<CredentialMapping> {
    const response = await apiClient.get<CredentialMapping>(`${basePath(tenantId)}/${id}`);
    return response.data;
  },

  async create(tenantId: string, data: CredentialMappingCreate): Promise<CredentialMapping> {
    const response = await apiClient.post<CredentialMapping>(basePath(tenantId), data);
    return response.data;
  },

  async update(
    tenantId: string,
    id: string,
    data: CredentialMappingUpdate
  ): Promise<CredentialMapping> {
    const response = await apiClient.put<CredentialMapping>(`${basePath(tenantId)}/${id}`, data);
    return response.data;
  },

  async delete(tenantId: string, id: string): Promise<void> {
    await apiClient.delete(`${basePath(tenantId)}/${id}`);
  },

  async listByConsumer(tenantId: string, consumerId: string): Promise<CredentialMapping[]> {
    const response = await apiClient.get<CredentialMapping[]>(
      `${basePath(tenantId)}/consumer/${consumerId}`
    );
    return response.data;
  },
};

export default credentialMappingsService;
