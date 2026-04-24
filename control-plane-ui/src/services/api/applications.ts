import { httpClient, path } from '../http';
import type { Application, ApplicationCreate } from '../../types';

export const applicationsClient = {
  async list(tenantId: string): Promise<Application[]> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'applications'), {
      params: { page: 1, page_size: 100 },
    });
    return data.items ?? data;
  },

  async get(tenantId: string, appId: string): Promise<Application> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'applications', appId));
    return data;
  },

  async create(tenantId: string, app: ApplicationCreate): Promise<Application> {
    const { data } = await httpClient.post(path('v1', 'tenants', tenantId, 'applications'), app);
    return data;
  },

  async update(
    tenantId: string,
    appId: string,
    patch: Partial<ApplicationCreate>
  ): Promise<Application> {
    const { data } = await httpClient.put(
      path('v1', 'tenants', tenantId, 'applications', appId),
      patch
    );
    return data;
  },

  async remove(tenantId: string, appId: string): Promise<void> {
    await httpClient.delete(path('v1', 'tenants', tenantId, 'applications', appId));
  },
};
