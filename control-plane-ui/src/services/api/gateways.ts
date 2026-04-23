import { httpClient } from '../http';

// Admin gateway instances (Control Plane Agnostique) + observability + policies.
// Typage laissé à `any` quand l'API ne fournit pas encore de Schemas['X']
// dédiés (UI-2 conserve la surface existante, pas de typage inventé).

export const gatewaysClient = {
  // Instances
  async listInstances(params?: {
    gateway_type?: string;
    environment?: string;
    tenant_id?: string;
    include_deleted?: boolean;
    page?: number;
    page_size?: number;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  }): Promise<{ items: any[]; total: number; page: number; page_size: number }> {
    const { data } = await httpClient.get('/v1/admin/gateways', { params });
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getInstance(id: string): Promise<any> {
    const { data } = await httpClient.get(`/v1/admin/gateways/${id}`);
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async listTools(id: string): Promise<any[]> {
    const { data } = await httpClient.get(`/v1/admin/gateways/${id}/tools`);
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async createInstance(payload: any): Promise<any> {
    const { data } = await httpClient.post('/v1/admin/gateways', payload);
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateInstance(id: string, payload: any): Promise<any> {
    const { data } = await httpClient.put(`/v1/admin/gateways/${id}`, payload);
    return data;
  },

  async removeInstance(id: string): Promise<void> {
    await httpClient.delete(`/v1/admin/gateways/${id}`);
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async restoreInstance(id: string): Promise<any> {
    const { data } = await httpClient.post(`/v1/admin/gateways/${id}/restore`);
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async checkHealth(id: string): Promise<any> {
    const { data } = await httpClient.post(`/v1/admin/gateways/${id}/health`);
    return data;
  },

  async getModeStats(): Promise<{
    modes: Array<{
      mode: string;
      total: number;
      online: number;
      offline: number;
      degraded: number;
    }>;
    total_gateways: number;
  }> {
    const { data } = await httpClient.get('/v1/admin/gateways/modes/stats');
    return data;
  },

  // Observability
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getAggregatedMetrics(): Promise<any> {
    const { data } = await httpClient.get('/v1/admin/gateways/metrics');
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGuardrailsEvents(limit = 20): Promise<any> {
    const { data } = await httpClient.get(
      `/v1/admin/gateways/metrics/guardrails/events?limit=${limit}`
    );
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getHealthSummary(): Promise<any> {
    const { data } = await httpClient.get('/v1/admin/gateways/health-summary');
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getInstanceMetrics(id: string): Promise<any> {
    const { data } = await httpClient.get(`/v1/admin/gateways/${id}/metrics`);
    return data;
  },

  // Policies
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async listPolicies(params?: { tenant_id?: string; environment?: string }): Promise<any[]> {
    const { data } = await httpClient.get('/v1/admin/policies', { params });
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async createPolicy(payload: any): Promise<any> {
    const { data } = await httpClient.post('/v1/admin/policies', payload);
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updatePolicy(id: string, payload: any): Promise<any> {
    const { data } = await httpClient.put(`/v1/admin/policies/${id}`, payload);
    return data;
  },

  async removePolicy(id: string): Promise<void> {
    await httpClient.delete(`/v1/admin/policies/${id}`);
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async createPolicyBinding(payload: any): Promise<any> {
    const { data } = await httpClient.post('/v1/admin/policies/bindings', payload);
    return data;
  },

  async removePolicyBinding(id: string): Promise<void> {
    await httpClient.delete(`/v1/admin/policies/bindings/${id}`);
  },
};
