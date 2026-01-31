import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { config } from '../config';
import type {
  Tenant, TenantCreate,
  API, APICreate,
  Application, ApplicationCreate,
  Deployment, DeploymentRequest,
  CommitInfo, MergeRequest,
  TraceSummary, PipelineTrace, TraceTimeline, TraceStats,
  ProspectListResponse, ProspectsMetricsResponse, ProspectDetail,
} from '../types';
import type { Client, ClientCreate, ClientWithCertificate, RotateRequest } from '../types/client';

const API_BASE_URL = config.api.baseUrl;

class ApiService {
  private client: AxiosInstance;
  private authToken: string | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Use request interceptor to ensure token is always attached
    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        console.log('[ApiService] Interceptor called, authToken exists:', !!this.authToken);
        if (this.authToken) {
          config.headers.Authorization = `Bearer ${this.authToken}`;
          console.log('[ApiService] Authorization header set');
        } else {
          console.warn('[ApiService] No auth token available for request to:', config.url);
        }
        return config;
      },
      (error) => Promise.reject(error)
    );
  }

  setAuthToken(token: string) {
    console.log('[ApiService] setAuthToken called');
    this.authToken = token;
    // Also set defaults for backwards compatibility
    this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  clearAuthToken() {
    this.authToken = null;
    delete this.client.defaults.headers.common['Authorization'];
  }

  // Generic HTTP methods for proxy services
  async get<T = any>(url: string, config?: { params?: Record<string, any> }): Promise<{ data: T }> {
    return this.client.get<T>(url, config);
  }

  async post<T = any>(url: string, data?: any): Promise<{ data: T }> {
    return this.client.post<T>(url, data);
  }

  async put<T = any>(url: string, data?: any): Promise<{ data: T }> {
    return this.client.put<T>(url, data);
  }

  async patch<T = any>(url: string, data?: any): Promise<{ data: T }> {
    return this.client.patch<T>(url, data);
  }

  async delete<T = any>(url: string): Promise<{ data: T }> {
    return this.client.delete<T>(url);
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

  // Platform Status (CAB-654)
  async getPlatformStatus(): Promise<PlatformStatusResponse> {
    const { data } = await this.client.get('/v1/platform/status');
    return data;
  }

  async getPlatformComponents(): Promise<ComponentStatus[]> {
    const { data } = await this.client.get('/v1/platform/components');
    return data;
  }

  async getComponentStatus(name: string): Promise<ComponentStatus> {
    const { data } = await this.client.get(`/v1/platform/components/${name}`);
    return data;
  }

  async syncPlatformComponent(name: string): Promise<{ message: string; operation: string }> {
    const { data } = await this.client.post(`/v1/platform/components/${name}/sync`);
    return data;
  }

  async getComponentDiff(name: string): Promise<ApplicationDiffResponse> {
    const { data } = await this.client.get(`/v1/platform/components/${name}/diff`);
    return data;
  }

  async getPlatformEvents(component?: string, limit?: number): Promise<PlatformEvent[]> {
    const params: Record<string, any> = {};
    if (component) params.component = component;
    if (limit) params.limit = limit;
    const { data } = await this.client.get('/v1/platform/events', { params });
    return data;
  }

  // Admin Prospects (CAB-911)
  async getProspects(params: {
    company?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    limit?: number;
  }): Promise<ProspectListResponse> {
    const { data } = await this.client.get('/v1/admin/prospects', { params });
    return data;
  }

  async getProspectsMetrics(params?: {
    date_from?: string;
    date_to?: string;
  }): Promise<ProspectsMetricsResponse> {
    const { data } = await this.client.get('/v1/admin/prospects/metrics', { params });
    return data;
  }

  async getProspect(inviteId: string): Promise<ProspectDetail> {
    const { data } = await this.client.get(`/v1/admin/prospects/${inviteId}`);
    return data;
  }

  async exportProspectsCSV(params?: {
    company?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<Blob> {
    const { data } = await this.client.get('/v1/admin/prospects/export', {
      params,
      responseType: 'blob',
    });
    return data;
  }

  // Clients (CAB-870)
  async getClients(): Promise<Client[]> {
    const { data } = await this.client.get('/v1/clients');
    return data;
  }

  async getClient(clientId: string): Promise<Client> {
    const { data } = await this.client.get(`/v1/clients/${clientId}`);
    return data;
  }

  async createClient(body: ClientCreate): Promise<ClientWithCertificate> {
    const { data } = await this.client.post('/v1/clients', body);
    return data;
  }

  async rotateClient(clientId: string, body: RotateRequest): Promise<ClientWithCertificate> {
    const { data } = await this.client.post(`/v1/clients/${clientId}/rotate`, body);
    return data;
  }

  async revokeClient(clientId: string): Promise<void> {
    await this.client.delete(`/v1/clients/${clientId}`);
  }
}

// Platform Status types (CAB-654)
export interface ComponentStatus {
  name: string;
  display_name: string;
  sync_status: string;
  health_status: string;
  revision: string;
  last_sync: string | null;
  message: string | null;
}

export interface GitOpsStatus {
  status: string;
  components: ComponentStatus[];
  checked_at: string;
}

export interface PlatformEvent {
  id: number | null;
  component: string;
  event_type: string;
  status: string;
  revision: string;
  message: string | null;
  timestamp: string;
  actor: string | null;
}

export interface ExternalLinks {
  argocd: string;
  grafana: string;
  prometheus: string;
  logs: string;
}

export interface PlatformStatusResponse {
  gitops: GitOpsStatus;
  events: PlatformEvent[];
  external_links: ExternalLinks;
  timestamp: string;
}

export interface ApplicationDiffResource {
  name: string;
  namespace: string | null;
  kind: string;
  group: string | null;
  status: string;
  health: string | null;
  diff: string | null;
}

export interface ApplicationDiffResponse {
  application: string;
  total_resources: number;
  diff_count: number;
  resources: ApplicationDiffResource[];
}

export const apiService = new ApiService();
