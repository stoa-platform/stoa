import { httpClient, path } from '../http';

// Admin-level gateway deployments — typed loosely (any) for parity with
// the pre-UI-2 surface. Strict typing to be addressed with Schemas when
// backend ships them.

export const gatewayDeploymentsClient = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getStatusSummary(): Promise<any> {
    const { data } = await httpClient.get('/v1/admin/deployments/status');
    return data;
  },

  async list(params?: {
    sync_status?: string;
    gateway_instance_id?: string;
    environment?: string;
    gateway_type?: string;
    page?: number;
    page_size?: number;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  }): Promise<{ items: any[]; total: number; page: number; page_size: number }> {
    const { data } = await httpClient.get('/v1/admin/deployments', { params });
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async get(id: string): Promise<any> {
    const { data } = await httpClient.get(path('v1', 'admin', 'deployments', id));
    return data;
  },

  async deployApiToGateways(payload: {
    api_catalog_id: string;
    gateway_instance_ids: string[];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  }): Promise<any[]> {
    const { data } = await httpClient.post('/v1/admin/deployments', payload);
    return data;
  },

  async undeploy(id: string): Promise<void> {
    await httpClient.delete(path('v1', 'admin', 'deployments', id));
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async forceSync(id: string): Promise<any> {
    const { data } = await httpClient.post(path('v1', 'admin', 'deployments', id, 'sync'));
    return data;
  },

  async test(id: string): Promise<{
    reachable: boolean;
    status_code?: number;
    latency_ms?: number;
    error?: string;
    gateway_url?: string;
    path?: string;
  }> {
    const { data } = await httpClient.post(path('v1', 'admin', 'deployments', id, 'test'));
    return data;
  },

  async listCatalogEntries(): Promise<
    { id: string; api_name: string; tenant_id: string; version: string }[]
  > {
    const { data } = await httpClient.get('/v1/admin/deployments/catalog-entries');
    return data;
  },
};
