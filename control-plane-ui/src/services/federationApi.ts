/**
 * Federation API Service (CAB-1372)
 *
 * Client for managing MCP Federation master accounts and sub-accounts.
 */

import { apiService } from './api';
import type {
  MasterAccount,
  MasterAccountCreate,
  MasterAccountUpdate,
  MasterAccountListResponse,
  SubAccount,
  SubAccountCreate,
  SubAccountCreatedResponse,
  SubAccountListResponse,
  ToolAllowListResponse,
  UsageResponse,
  FederationBulkRevokeResponse,
} from '../types';

class FederationService {
  // ==========================================================================
  // Master Account Operations
  // ==========================================================================

  /**
   * List master accounts for a tenant.
   * Endpoint: GET /v1/tenants/{tenant_id}/federation/accounts
   */
  async listMasterAccounts(tenantId: string): Promise<MasterAccountListResponse> {
    const { data } = await apiService.get(`/v1/tenants/${tenantId}/federation/accounts`);
    return data;
  }

  /**
   * Get a specific master account.
   * Endpoint: GET /v1/tenants/{tenant_id}/federation/accounts/{id}
   */
  async getMasterAccount(tenantId: string, id: string): Promise<MasterAccount> {
    const { data } = await apiService.get(`/v1/tenants/${tenantId}/federation/accounts/${id}`);
    return data;
  }

  /**
   * Create a new master account.
   * Endpoint: POST /v1/tenants/{tenant_id}/federation/accounts
   */
  async createMasterAccount(
    tenantId: string,
    payload: MasterAccountCreate
  ): Promise<MasterAccount> {
    const { data } = await apiService.post(`/v1/tenants/${tenantId}/federation/accounts`, payload);
    return data;
  }

  /**
   * Update a master account.
   * Endpoint: PATCH /v1/tenants/{tenant_id}/federation/accounts/{id}
   */
  async updateMasterAccount(
    tenantId: string,
    id: string,
    payload: MasterAccountUpdate
  ): Promise<MasterAccount> {
    const { data } = await apiService.patch(
      `/v1/tenants/${tenantId}/federation/accounts/${id}`,
      payload
    );
    return data;
  }

  /**
   * Delete a master account.
   * Endpoint: DELETE /v1/tenants/{tenant_id}/federation/accounts/{id}
   */
  async deleteMasterAccount(tenantId: string, id: string): Promise<void> {
    await apiService.delete(`/v1/tenants/${tenantId}/federation/accounts/${id}`);
  }

  // ==========================================================================
  // Sub-Account Operations
  // ==========================================================================

  /**
   * List sub-accounts for a master account.
   * Endpoint: GET /v1/tenants/{tenant_id}/federation/accounts/{masterId}/sub-accounts
   */
  async listSubAccounts(tenantId: string, masterId: string): Promise<SubAccountListResponse> {
    const { data } = await apiService.get(
      `/v1/tenants/${tenantId}/federation/accounts/${masterId}/sub-accounts`
    );
    return data;
  }

  /**
   * Create a sub-account (returns one-time API key).
   * Endpoint: POST /v1/tenants/{tenant_id}/federation/accounts/{masterId}/sub-accounts
   */
  async createSubAccount(
    tenantId: string,
    masterId: string,
    payload: SubAccountCreate
  ): Promise<SubAccountCreatedResponse> {
    const { data } = await apiService.post(
      `/v1/tenants/${tenantId}/federation/accounts/${masterId}/sub-accounts`,
      payload
    );
    return data;
  }

  /**
   * Revoke a sub-account.
   * Endpoint: POST /v1/tenants/{tenant_id}/federation/accounts/{masterId}/sub-accounts/{subId}/revoke
   */
  async revokeSubAccount(tenantId: string, masterId: string, subId: string): Promise<SubAccount> {
    const { data } = await apiService.post(
      `/v1/tenants/${tenantId}/federation/accounts/${masterId}/sub-accounts/${subId}/revoke`
    );
    return data;
  }

  // ==========================================================================
  // Tool Allow-List Operations
  // ==========================================================================

  /**
   * Get the tool allow-list for a sub-account.
   * Endpoint: GET /v1/tenants/{tenant_id}/federation/accounts/{masterId}/sub-accounts/{subId}/tools
   */
  async getToolAllowList(
    tenantId: string,
    masterId: string,
    subId: string
  ): Promise<ToolAllowListResponse> {
    const { data } = await apiService.get(
      `/v1/tenants/${tenantId}/federation/accounts/${masterId}/sub-accounts/${subId}/tools`
    );
    return data;
  }

  /**
   * Update the tool allow-list for a sub-account.
   * Endpoint: PUT /v1/tenants/{tenant_id}/federation/accounts/{masterId}/sub-accounts/{subId}/tools
   */
  async updateToolAllowList(
    tenantId: string,
    masterId: string,
    subId: string,
    tools: string[]
  ): Promise<ToolAllowListResponse> {
    const { data } = await apiService.put(
      `/v1/tenants/${tenantId}/federation/accounts/${masterId}/sub-accounts/${subId}/tools`,
      { allowed_tools: tools }
    );
    return data;
  }
  // ==========================================================================
  // Usage & Bulk Operations
  // ==========================================================================

  /**
   * Get usage stats for a master account.
   * Endpoint: GET /v1/tenants/{tenant_id}/federation/accounts/{masterId}/usage
   */
  async getUsage(tenantId: string, masterId: string, days = 7): Promise<UsageResponse> {
    const { data } = await apiService.get(
      `/v1/tenants/${tenantId}/federation/accounts/${masterId}/usage`,
      { params: { days } }
    );
    return data;
  }

  /**
   * Bulk revoke all active sub-accounts.
   * Endpoint: POST /v1/tenants/{tenant_id}/federation/accounts/{masterId}/bulk-revoke
   */
  async bulkRevoke(tenantId: string, masterId: string): Promise<FederationBulkRevokeResponse> {
    const { data } = await apiService.post(
      `/v1/tenants/${tenantId}/federation/accounts/${masterId}/bulk-revoke`
    );
    return data;
  }
}

export const federationService = new FederationService();
