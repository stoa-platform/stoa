/**
 * Backend APIs & SaaS API Keys Service (CAB-1188/CAB-1251)
 *
 * Client for managing backend API registrations and scoped API keys
 * via the Control-Plane-API.
 */

import { apiService } from './api';
import type {
  BackendApi,
  BackendApiCreate,
  BackendApiUpdate,
  BackendApiListResponse,
  SaasApiKeyCreate,
  SaasApiKeyCreatedResponse,
  SaasApiKeyListResponse,
} from '../types';

class BackendApisService {
  // ==========================================================================
  // Backend API CRUD
  // ==========================================================================

  async listBackendApis(
    tenantId: string,
    params?: { page?: number; page_size?: number; status?: string }
  ): Promise<BackendApiListResponse> {
    const { data } = await apiService.get(`/v1/tenants/${tenantId}/backend-apis`, {
      params: {
        page: params?.page || 1,
        page_size: params?.page_size || 50,
        status: params?.status,
      },
    });
    return data;
  }

  async createBackendApi(tenantId: string, api: BackendApiCreate): Promise<BackendApi> {
    const { data } = await apiService.post(`/v1/tenants/${tenantId}/backend-apis`, api);
    return data;
  }

  async updateBackendApi(
    tenantId: string,
    apiId: string,
    update: BackendApiUpdate
  ): Promise<BackendApi> {
    const { data } = await apiService.patch(
      `/v1/tenants/${tenantId}/backend-apis/${apiId}`,
      update
    );
    return data;
  }

  async deleteBackendApi(tenantId: string, apiId: string): Promise<void> {
    await apiService.delete(`/v1/tenants/${tenantId}/backend-apis/${apiId}`);
  }

  // ==========================================================================
  // SaaS API Keys
  // ==========================================================================

  async listSaasKeys(
    tenantId: string,
    params?: { page?: number; page_size?: number }
  ): Promise<SaasApiKeyListResponse> {
    const { data } = await apiService.get(`/v1/tenants/${tenantId}/saas-keys`, {
      params: {
        page: params?.page || 1,
        page_size: params?.page_size || 50,
      },
    });
    return data;
  }

  async createSaasKey(tenantId: string, key: SaasApiKeyCreate): Promise<SaasApiKeyCreatedResponse> {
    const { data } = await apiService.post(`/v1/tenants/${tenantId}/saas-keys`, key);
    return data;
  }

  async revokeSaasKey(tenantId: string, keyId: string): Promise<void> {
    await apiService.delete(`/v1/tenants/${tenantId}/saas-keys/${keyId}`);
  }
}

export const backendApisService = new BackendApisService();
