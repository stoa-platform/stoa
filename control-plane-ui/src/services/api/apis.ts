import { httpClient, path } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type { API, APICreate, Environment } from '../../types';

export const apisClient = {
  async list(tenantId: string, environment?: Environment): Promise<API[]> {
    const params: Record<string, unknown> = { page: 1, page_size: 100 };
    if (environment) params.environment = environment;
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'apis'), { params });
    return data.items ?? data;
  },

  async listAdmin(page = 1, pageSize = 100): Promise<API[]> {
    const { data } = await httpClient.get('/v1/admin/catalog/apis', {
      params: { page, page_size: pageSize },
    });
    return data.items ?? data;
  },

  async get(tenantId: string, apiId: string): Promise<API> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'apis', apiId));
    return data;
  },

  async create(tenantId: string, api: APICreate): Promise<API> {
    const { data } = await httpClient.post(path('v1', 'tenants', tenantId, 'apis'), api);
    return data;
  },

  async update(tenantId: string, apiId: string, api: Partial<APICreate>): Promise<API> {
    const { data } = await httpClient.put(path('v1', 'tenants', tenantId, 'apis', apiId), api);
    return data;
  },

  async remove(tenantId: string, apiId: string): Promise<void> {
    await httpClient.delete(path('v1', 'tenants', tenantId, 'apis', apiId));
  },

  async listVersions(
    tenantId: string,
    apiId: string,
    limit = 20
  ): Promise<Schemas['APIVersionEntry'][]> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'versions'),
      {
        params: { limit },
      }
    );
    return data;
  },

  async updateAudience(
    tenantId: string,
    apiId: string,
    audience: string
  ): Promise<{ api_id: string; tenant_id: string; audience: string; updated_by: string }> {
    const { data } = await httpClient.patch(
      path('v1', 'admin', 'catalog', tenantId, apiId, 'audience'),
      {
        audience,
      }
    );
    return data;
  },

  async triggerCatalogSync(tenantId: string): Promise<void> {
    await httpClient.post(path('v1', 'admin', 'catalog', 'sync', 'tenant', tenantId));
  },
};
