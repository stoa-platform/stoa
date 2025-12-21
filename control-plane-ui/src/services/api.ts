import axios, { AxiosInstance } from 'axios';
import type {
  Tenant, TenantCreate,
  API, APICreate,
  Application, ApplicationCreate,
  Deployment, DeploymentRequest,
  CommitInfo, MergeRequest,
  TraceSummary, PipelineTrace, TraceTimeline, TraceStats
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

class ApiService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  setAuthToken(token: string) {
    this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  clearAuthToken() {
    delete this.client.defaults.headers.common['Authorization'];
  }

  // Tenants
  async getTenants(): Promise<Tenant[]> {
    const { data } = await this.client.get('/v1/tenants');
    return data;
  }

  async getTenant(tenantId: string): Promise<Tenant> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}`);
    return data;
  }

  async createTenant(tenant: TenantCreate): Promise<Tenant> {
    const { data } = await this.client.post('/v1/tenants', tenant);
    return data;
  }

  async updateTenant(tenantId: string, tenant: Partial<TenantCreate>): Promise<Tenant> {
    const { data } = await this.client.put(`/v1/tenants/${tenantId}`, tenant);
    return data;
  }

  async deleteTenant(tenantId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}`);
  }

  // APIs
  async getApis(tenantId: string): Promise<API[]> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/apis`);
    return data;
  }

  async getApi(tenantId: string, apiId: string): Promise<API> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/apis/${apiId}`);
    return data;
  }

  async createApi(tenantId: string, api: APICreate): Promise<API> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/apis`, api);
    return data;
  }

  async updateApi(tenantId: string, apiId: string, api: Partial<APICreate>): Promise<API> {
    const { data } = await this.client.put(`/v1/tenants/${tenantId}/apis/${apiId}`, api);
    return data;
  }

  async deleteApi(tenantId: string, apiId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/apis/${apiId}`);
  }

  // Applications
  async getApplications(tenantId: string): Promise<Application[]> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/applications`);
    return data;
  }

  async getApplication(tenantId: string, appId: string): Promise<Application> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/applications/${appId}`);
    return data;
  }

  async createApplication(tenantId: string, app: ApplicationCreate): Promise<Application> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/applications`, app);
    return data;
  }

  async updateApplication(tenantId: string, appId: string, app: Partial<ApplicationCreate>): Promise<Application> {
    const { data } = await this.client.put(`/v1/tenants/${tenantId}/applications/${appId}`, app);
    return data;
  }

  async deleteApplication(tenantId: string, appId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/applications/${appId}`);
  }

  // Deployments
  async getDeployments(tenantId: string, apiId?: string): Promise<Deployment[]> {
    const params = apiId ? { api_id: apiId } : {};
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/deployments`, { params });
    return data;
  }

  async createDeployment(tenantId: string, request: DeploymentRequest): Promise<Deployment> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/deployments`, request);
    return data;
  }

  async rollbackDeployment(tenantId: string, deploymentId: string, targetVersion?: string): Promise<Deployment> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/deployments/${deploymentId}/rollback`,
      { target_version: targetVersion }
    );
    return data;
  }

  // Git
  async getCommits(tenantId: string, path?: string): Promise<CommitInfo[]> {
    const params = path ? { path } : {};
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/git/commits`, { params });
    return data;
  }

  async getMergeRequests(tenantId: string): Promise<MergeRequest[]> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/git/merge-requests`);
    return data;
  }

  // SSE Events
  createEventSource(tenantId: string, eventTypes?: string[]): EventSource {
    const params = eventTypes ? `?event_types=${eventTypes.join(',')}` : '';
    const url = `${API_BASE_URL}/v1/events/stream/${tenantId}${params}`;
    return new EventSource(url);
  }

  // Pipeline Traces
  async getTraces(limit?: number, tenantId?: string, status?: string): Promise<{ traces: TraceSummary[], total: number }> {
    const params: Record<string, any> = {};
    if (limit) params.limit = limit;
    if (tenantId) params.tenant_id = tenantId;
    if (status) params.status = status;
    const { data } = await this.client.get('/v1/traces', { params });
    return data;
  }

  async getTrace(traceId: string): Promise<PipelineTrace> {
    const { data } = await this.client.get(`/v1/traces/${traceId}`);
    return data;
  }

  async getTraceTimeline(traceId: string): Promise<TraceTimeline> {
    const { data } = await this.client.get(`/v1/traces/${traceId}/timeline`);
    return data;
  }

  async getTraceStats(): Promise<TraceStats> {
    const { data } = await this.client.get('/v1/traces/stats');
    return data;
  }

  async getLiveTraces(): Promise<{ traces: PipelineTrace[], count: number }> {
    const { data } = await this.client.get('/v1/traces/live');
    return data;
  }
}

export const apiService = new ApiService();
