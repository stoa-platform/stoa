import { httpClient, path } from '../http';
import type {
  DeploymentStatusSummary,
  GatewayDeployment,
  PaginatedGatewayDeployments,
} from '../../types';

// Admin-level gateway deployments. CAB-2164 replaced the `any` surface with
// shared schemas (`Schemas['PaginatedGatewayDeployments']`) and local UI
// types (`GatewayDeployment` narrows `desired_state`/`actual_state` with an
// index signature, per P2-E UI-1 W1). `getStatusSummary` remains a local
// wrapper pending a canonical backend schema (see BACKEND-GAPS-CAB-2159.md
// §BUG-8).

export const gatewayDeploymentsClient = {
  async getStatusSummary(): Promise<DeploymentStatusSummary> {
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
  }): Promise<PaginatedGatewayDeployments> {
    const { data } = await httpClient.get('/v1/admin/deployments', { params });
    return data;
  },

  async get(id: string): Promise<GatewayDeployment> {
    const { data } = await httpClient.get(path('v1', 'admin', 'deployments', id));
    return data;
  },

  async deployApiToGateways(payload: {
    api_catalog_id: string;
    gateway_instance_ids: string[];
  }): Promise<GatewayDeployment[]> {
    const { data } = await httpClient.post('/v1/admin/deployments', payload);
    return data;
  },

  async undeploy(id: string): Promise<void> {
    await httpClient.delete(path('v1', 'admin', 'deployments', id));
  },

  async forceSync(id: string): Promise<GatewayDeployment> {
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
