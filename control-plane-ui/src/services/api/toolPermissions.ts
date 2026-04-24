import { httpClient, path } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type { TenantToolPermission, TenantToolPermissionListResponse } from '../../types';

export const toolPermissionsClient = {
  async list(
    tenantId: string,
    params?: { mcp_server_id?: string; page?: number; page_size?: number }
  ): Promise<TenantToolPermissionListResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'tool-permissions'), {
      params: { ...params, page_size: params?.page_size ?? 100 },
    });
    return data;
  },

  async upsert(
    tenantId: string,
    body: Schemas['TenantToolPermissionCreate']
  ): Promise<TenantToolPermission> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'tool-permissions'),
      body
    );
    return data;
  },

  async remove(tenantId: string, permissionId: string): Promise<void> {
    await httpClient.delete(path('v1', 'tenants', tenantId, 'tool-permissions', permissionId));
  },
};
