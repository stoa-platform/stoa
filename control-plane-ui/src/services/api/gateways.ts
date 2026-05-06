import type { Schemas } from '@stoa/shared/api-types';
import { httpClient, path } from '../http';
import type {
  AggregatedMetrics,
  GatewayGuardrailsResponse,
  GatewayHealthSummary,
  GatewayInstance,
  GatewayInstanceCreate,
  GatewayInstanceMetrics,
  GatewayInstanceUpdate,
  GatewayModeStats,
  GatewayOverviewResponse,
  GatewayPolicy,
  PaginatedGatewayInstances,
} from '../../types';

// Admin gateway instances (Control Plane Agnostique) + observability + policies.
// CAB-2164 hardened the typing surface: every response is typed against a
// shared `Schemas[...]` alias or a local wrapper that lives in
// `src/types/index.ts`. The four wrappers (GatewayGuardrailsResponse,
// GatewayInstanceMetrics, DeploymentStatusSummary, plus listTools return)
// carry TODO(WAVE-2) markers pointing at BACKEND-GAPS-CAB-2159.md entries.

export const gatewaysClient = {
  // Instances
  async listInstances(params?: {
    gateway_type?: string;
    environment?: string;
    tenant_id?: string;
    include_deleted?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedGatewayInstances> {
    const { data } = await httpClient.get('/v1/admin/gateways', { params });
    return data;
  },

  async getInstance(id: string): Promise<GatewayInstance> {
    const { data } = await httpClient.get(path('v1', 'admin', 'gateways', id));
    return data;
  },

  async getOverview(id: string): Promise<GatewayOverviewResponse> {
    const { data } = await httpClient.get(path('v1', 'admin', 'gateways', id, 'overview'));
    return data;
  },

  async listTools(id: string): Promise<Schemas['ListToolsResponse']['tools']> {
    const { data } = await httpClient.get(path('v1', 'admin', 'gateways', id, 'tools'));
    return data;
  },

  async createInstance(payload: GatewayInstanceCreate): Promise<GatewayInstance> {
    const { data } = await httpClient.post('/v1/admin/gateways', payload);
    return data;
  },

  async updateInstance(id: string, payload: GatewayInstanceUpdate): Promise<GatewayInstance> {
    const { data } = await httpClient.put(path('v1', 'admin', 'gateways', id), payload);
    return data;
  },

  async removeInstance(id: string): Promise<void> {
    await httpClient.delete(path('v1', 'admin', 'gateways', id));
  },

  async restoreInstance(id: string): Promise<GatewayInstance> {
    const { data } = await httpClient.post(path('v1', 'admin', 'gateways', id, 'restore'));
    return data;
  },

  async checkHealth(id: string): Promise<Schemas['GatewayHealthCheckResponse']> {
    const { data } = await httpClient.post(path('v1', 'admin', 'gateways', id, 'health'));
    return data;
  },

  async getModeStats(): Promise<GatewayModeStats> {
    const { data } = await httpClient.get('/v1/admin/gateways/modes/stats');
    return data;
  },

  // Observability
  async getAggregatedMetrics(): Promise<AggregatedMetrics> {
    const { data } = await httpClient.get('/v1/admin/gateways/metrics');
    return data;
  },

  async getGuardrailsEvents(limit = 20): Promise<GatewayGuardrailsResponse> {
    // P1-11 residu: use axios params option rather than inline template string.
    const { data } = await httpClient.get('/v1/admin/gateways/metrics/guardrails/events', {
      params: { limit },
    });
    return data;
  },

  async getHealthSummary(): Promise<GatewayHealthSummary> {
    const { data } = await httpClient.get('/v1/admin/gateways/health-summary');
    return data;
  },

  async getInstanceMetrics(id: string): Promise<GatewayInstanceMetrics> {
    const { data } = await httpClient.get(path('v1', 'admin', 'gateways', id, 'metrics'));
    return data;
  },

  // Policies
  async listPolicies(params?: {
    tenant_id?: string;
    environment?: string;
  }): Promise<GatewayPolicy[]> {
    const { data } = await httpClient.get('/v1/admin/policies', { params });
    return data;
  },

  async createPolicy(payload: Schemas['GatewayPolicyCreate']): Promise<GatewayPolicy> {
    const { data } = await httpClient.post('/v1/admin/policies', payload);
    return data;
  },

  async updatePolicy(id: string, payload: Schemas['GatewayPolicyUpdate']): Promise<GatewayPolicy> {
    const { data } = await httpClient.put(path('v1', 'admin', 'policies', id), payload);
    return data;
  },

  async removePolicy(id: string): Promise<void> {
    await httpClient.delete(path('v1', 'admin', 'policies', id));
  },

  async createPolicyBinding(
    payload: Schemas['PolicyBindingCreate']
  ): Promise<Schemas['PolicyBindingResponse']> {
    const { data } = await httpClient.post('/v1/admin/policies/bindings', payload);
    return data;
  },

  async removePolicyBinding(id: string): Promise<void> {
    await httpClient.delete(path('v1', 'admin', 'policies', 'bindings', id));
  },
};
