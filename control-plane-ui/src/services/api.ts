import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { config } from '../config';
import type {
  Tenant,
  TenantCreate,
  API,
  APICreate,
  Application,
  ApplicationCreate,
  Consumer,
  CertificateExpiryResponse,
  BulkRevokeResponse,
  Deployment,
  DeploymentCreate,
  DeploymentListResponse,
  DeploymentLogListResponse,
  EnvironmentStatusResponse,
  CommitInfo,
  MergeRequest,
  TraceSummary,
  PipelineTrace,
  TraceTimeline,
  TraceStats,
  ProspectListResponse,
  ProspectsMetricsResponse,
  ProspectDetail,
  Environment,
  EnvironmentConfig,
  WorkflowTemplate,
  WorkflowTemplateCreate,
  WorkflowTemplateUpdate,
  WorkflowInstance,
  WorkflowTemplateListResponse,
  WorkflowListResponse,
} from '../types';

const API_BASE_URL = config.api.baseUrl;

type TokenRefresher = () => Promise<string | null>;

class ApiService {
  private client: AxiosInstance;
  private authToken: string | null = null;
  private tokenRefresher: TokenRefresher | null = null;
  private isRefreshing = false;
  private refreshQueue: Array<{
    resolve: (token: string | null) => void;
    reject: (error: unknown) => void;
  }> = [];

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
        if (this.authToken) {
          config.headers.Authorization = `Bearer ${this.authToken}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // CAB-1122: Response interceptor for 401 token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
        if (
          error.response?.status === 401 &&
          originalRequest &&
          !originalRequest._retry &&
          this.tokenRefresher
        ) {
          if (this.isRefreshing) {
            return new Promise((resolve, reject) => {
              this.refreshQueue.push({ resolve, reject });
            }).then((token) => {
              if (token && originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${token}`;
              }
              return this.client(originalRequest);
            });
          }

          originalRequest._retry = true;
          this.isRefreshing = true;

          try {
            const newToken = await this.tokenRefresher();
            if (newToken) {
              this.setAuthToken(newToken);
              this.refreshQueue.forEach(({ resolve }) => resolve(newToken));
              this.refreshQueue = [];
              if (originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${newToken}`;
              }
              return this.client(originalRequest);
            }
          } catch (refreshError) {
            this.refreshQueue.forEach(({ reject }) => reject(refreshError));
            this.refreshQueue = [];
            return Promise.reject(refreshError);
          } finally {
            this.isRefreshing = false;
          }
        }
        return Promise.reject(error);
      }
    );
  }

  setTokenRefresher(refresher: TokenRefresher) {
    this.tokenRefresher = refresher;
  }

  setAuthToken(token: string) {
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

  // Environments (ADR-040)
  async getEnvironments(): Promise<EnvironmentConfig[]> {
    const { data } = await this.client.get('/v1/environments');
    return data.environments;
  }

  // APIs
  async getApis(tenantId: string, environment?: Environment): Promise<API[]> {
    const params: Record<string, unknown> = { page: 1, page_size: 100 };
    if (environment) params.environment = environment;
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/apis`, { params });
    return data.items ?? data;
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

  async updateApiAudience(
    tenantId: string,
    apiId: string,
    audience: string
  ): Promise<{ api_id: string; tenant_id: string; audience: string; updated_by: string }> {
    const { data } = await this.client.patch(`/v1/admin/catalog/${tenantId}/${apiId}/audience`, {
      audience,
    });
    return data;
  }

  // Applications
  async getApplications(tenantId: string): Promise<Application[]> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/applications`, {
      params: { page: 1, page_size: 100 },
    });
    return data.items ?? data;
  }

  async getApplication(tenantId: string, appId: string): Promise<Application> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/applications/${appId}`);
    return data;
  }

  async createApplication(tenantId: string, app: ApplicationCreate): Promise<Application> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/applications`, app);
    return data;
  }

  async updateApplication(
    tenantId: string,
    appId: string,
    app: Partial<ApplicationCreate>
  ): Promise<Application> {
    const { data } = await this.client.put(`/v1/tenants/${tenantId}/applications/${appId}`, app);
    return data;
  }

  async deleteApplication(tenantId: string, appId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/applications/${appId}`);
  }

  // Consumers (CAB-864 — mTLS Self-Service)
  async getConsumers(tenantId: string): Promise<Consumer[]> {
    const { data } = await this.client.get(`/v1/consumers/${tenantId}`, {
      params: { page: 1, page_size: 100 },
    });
    return data.items ?? data;
  }

  async getConsumer(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await this.client.get(`/v1/consumers/${tenantId}/${consumerId}`);
    return data;
  }

  async suspendConsumer(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await this.client.post(`/v1/consumers/${tenantId}/${consumerId}/suspend`);
    return data;
  }

  async activateConsumer(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await this.client.post(`/v1/consumers/${tenantId}/${consumerId}/activate`);
    return data;
  }

  async deleteConsumer(tenantId: string, consumerId: string): Promise<void> {
    await this.client.delete(`/v1/consumers/${tenantId}/${consumerId}`);
  }

  async rotateCertificate(
    tenantId: string,
    consumerId: string,
    certificatePem: string,
    gracePeriodHours: number = 24
  ): Promise<Consumer> {
    const { data } = await this.client.post(
      `/v1/consumers/${tenantId}/${consumerId}/certificate/rotate`,
      { certificate_pem: certificatePem, grace_period_hours: gracePeriodHours }
    );
    return data;
  }

  async revokeCertificate(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await this.client.post(
      `/v1/consumers/${tenantId}/${consumerId}/certificate/revoke`
    );
    return data;
  }

  async blockConsumer(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await this.client.post(`/v1/consumers/${tenantId}/${consumerId}/block`);
    return data;
  }

  // Certificate Lifecycle (CAB-872)
  async bindCertificate(
    tenantId: string,
    consumerId: string,
    certificatePem: string
  ): Promise<Consumer> {
    const { data } = await this.client.post(`/v1/consumers/${tenantId}/${consumerId}/certificate`, {
      certificate_pem: certificatePem,
    });
    return data;
  }

  async getExpiringCertificates(
    tenantId: string,
    days: number = 30
  ): Promise<CertificateExpiryResponse> {
    const { data } = await this.client.get(`/v1/consumers/${tenantId}/certificates/expiring`, {
      params: { days },
    });
    return data;
  }

  async bulkRevokeCertificates(
    tenantId: string,
    consumerIds: string[]
  ): Promise<BulkRevokeResponse> {
    const { data } = await this.client.post(`/v1/consumers/${tenantId}/certificates/bulk-revoke`, {
      consumer_ids: consumerIds,
    });
    return data;
  }

  // Deployments (CAB-1353 lifecycle API)
  async listDeployments(
    tenantId: string,
    params?: {
      api_id?: string;
      environment?: string;
      status?: string;
      page?: number;
      page_size?: number;
    }
  ): Promise<DeploymentListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/deployments`, { params });
    return data;
  }

  async getDeployment(tenantId: string, deploymentId: string): Promise<Deployment> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/deployments/${deploymentId}`);
    return data;
  }

  async createDeployment(tenantId: string, request: DeploymentCreate): Promise<Deployment> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/deployments`, request);
    return data;
  }

  async rollbackDeployment(
    tenantId: string,
    deploymentId: string,
    targetVersion?: string
  ): Promise<Deployment> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/deployments/${deploymentId}/rollback`,
      { target_version: targetVersion }
    );
    return data;
  }

  async getDeploymentLogs(
    tenantId: string,
    deploymentId: string,
    afterSeq: number = 0,
    limit: number = 200
  ): Promise<DeploymentLogListResponse> {
    const { data } = await this.client.get(
      `/v1/tenants/${tenantId}/deployments/${deploymentId}/logs`,
      { params: { after_seq: afterSeq, limit } }
    );
    return data;
  }

  async getEnvironmentStatus(
    tenantId: string,
    environment: string
  ): Promise<EnvironmentStatusResponse> {
    const { data } = await this.client.get(
      `/v1/tenants/${tenantId}/deployments/environments/${environment}/status`
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
  async getTraces(
    limit?: number,
    tenantId?: string,
    status?: string
  ): Promise<{ traces: TraceSummary[]; total: number }> {
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

  async getLiveTraces(): Promise<{ traces: PipelineTrace[]; count: number }> {
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

  // Gateway Instances (Control Plane Agnostique)
  async getGatewayInstances(params?: {
    gateway_type?: string;
    environment?: string;
    tenant_id?: string;
    page?: number;
    page_size?: number;
  }): Promise<{ items: any[]; total: number; page: number; page_size: number }> {
    const { data } = await this.client.get('/v1/admin/gateways', { params });
    return data;
  }

  async getGatewayInstance(id: string): Promise<any> {
    const { data } = await this.client.get(`/v1/admin/gateways/${id}`);
    return data;
  }

  async createGatewayInstance(payload: any): Promise<any> {
    const { data } = await this.client.post('/v1/admin/gateways', payload);
    return data;
  }

  async updateGatewayInstance(id: string, payload: any): Promise<any> {
    const { data } = await this.client.put(`/v1/admin/gateways/${id}`, payload);
    return data;
  }

  async deleteGatewayInstance(id: string): Promise<void> {
    await this.client.delete(`/v1/admin/gateways/${id}`);
  }

  async checkGatewayHealth(id: string): Promise<any> {
    const { data } = await this.client.post(`/v1/admin/gateways/${id}/health`);
    return data;
  }

  async getGatewayModeStats(): Promise<{
    modes: Array<{
      mode: string;
      total: number;
      online: number;
      offline: number;
      degraded: number;
    }>;
    total_gateways: number;
  }> {
    const { data } = await this.client.get('/v1/admin/gateways/modes/stats');
    return data;
  }

  // Gateway Deployments
  async getDeploymentStatusSummary(): Promise<any> {
    const { data } = await this.client.get('/v1/admin/deployments/status');
    return data;
  }

  async getGatewayDeployments(params?: {
    sync_status?: string;
    gateway_instance_id?: string;
    page?: number;
    page_size?: number;
  }): Promise<{ items: any[]; total: number; page: number; page_size: number }> {
    const { data } = await this.client.get('/v1/admin/deployments', { params });
    return data;
  }

  async getGatewayDeployment(id: string): Promise<any> {
    const { data } = await this.client.get(`/v1/admin/deployments/${id}`);
    return data;
  }

  async deployApiToGateways(payload: {
    api_catalog_id: string;
    gateway_instance_ids: string[];
  }): Promise<any[]> {
    const { data } = await this.client.post('/v1/admin/deployments', payload);
    return data;
  }

  async undeployFromGateway(id: string): Promise<void> {
    await this.client.delete(`/v1/admin/deployments/${id}`);
  }

  async forceSyncDeployment(id: string): Promise<any> {
    const { data } = await this.client.post(`/v1/admin/deployments/${id}/sync`);
    return data;
  }

  async getCatalogEntries(): Promise<
    { id: string; api_name: string; tenant_id: string; version: string }[]
  > {
    const { data } = await this.client.get('/v1/admin/deployments/catalog-entries');
    return data;
  }

  // =========================================================================
  // Gateway Observability
  // =========================================================================

  async getGatewayAggregatedMetrics(): Promise<any> {
    const { data } = await this.client.get('/v1/admin/gateways/metrics');
    return data;
  }

  async getGatewayHealthSummary(): Promise<any> {
    const { data } = await this.client.get('/v1/admin/gateways/health-summary');
    return data;
  }

  async getGatewayInstanceMetrics(id: string): Promise<any> {
    const { data } = await this.client.get(`/v1/admin/gateways/${id}/metrics`);
    return data;
  }

  // =========================================================================
  // Gateway Policies
  // =========================================================================

  async getGatewayPolicies(params?: { tenant_id?: string }): Promise<any[]> {
    const { data } = await this.client.get('/v1/admin/policies', { params });
    return data;
  }

  async createGatewayPolicy(payload: any): Promise<any> {
    const { data } = await this.client.post('/v1/admin/policies', payload);
    return data;
  }

  async updateGatewayPolicy(id: string, payload: any): Promise<any> {
    const { data } = await this.client.put(`/v1/admin/policies/${id}`, payload);
    return data;
  }

  async deleteGatewayPolicy(id: string): Promise<void> {
    await this.client.delete(`/v1/admin/policies/${id}`);
  }

  async createPolicyBinding(payload: any): Promise<any> {
    const { data } = await this.client.post('/v1/admin/policies/bindings', payload);
    return data;
  }

  async deletePolicyBinding(id: string): Promise<void> {
    await this.client.delete(`/v1/admin/policies/bindings/${id}`);
  }

  // =========================================================================
  // Operations Dashboard (CAB-Observability)
  // =========================================================================

  async getOperationsMetrics(): Promise<OperationsMetrics> {
    const { data } = await this.client.get('/v1/operations/metrics');
    return data;
  }

  // =========================================================================
  // Business Analytics (CAB-Observability)
  // =========================================================================

  async getBusinessMetrics(): Promise<BusinessMetrics> {
    const { data } = await this.client.get('/v1/business/metrics');
    return data;
  }

  async getTopAPIs(limit = 10): Promise<TopAPI[]> {
    const { data } = await this.client.get(`/v1/business/top-apis?limit=${limit}`);
    return data;
  }

  // Workflow Engine methods (CAB-593)
  async listWorkflowTemplates(tenantId: string): Promise<WorkflowTemplateListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/workflows/templates`);
    return data;
  }

  async createWorkflowTemplate(
    tenantId: string,
    payload: WorkflowTemplateCreate
  ): Promise<WorkflowTemplate> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/workflows/templates`, payload);
    return data;
  }

  async updateWorkflowTemplate(
    tenantId: string,
    templateId: string,
    payload: WorkflowTemplateUpdate
  ): Promise<WorkflowTemplate> {
    const { data } = await this.client.put(
      `/v1/tenants/${tenantId}/workflows/templates/${templateId}`,
      payload
    );
    return data;
  }

  async deleteWorkflowTemplate(tenantId: string, templateId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/workflows/templates/${templateId}`);
  }

  async listWorkflowInstances(
    tenantId: string,
    params?: { status?: string; skip?: number; limit?: number }
  ): Promise<WorkflowListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/workflows/instances`, {
      params,
    });
    return data;
  }

  async startWorkflow(
    tenantId: string,
    payload: { template_id: string; subject_id: string; subject_email: string }
  ): Promise<WorkflowInstance> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/workflows/instances`, payload);
    return data;
  }

  async approveWorkflowStep(
    tenantId: string,
    instanceId: string,
    payload: { comment?: string }
  ): Promise<WorkflowInstance> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/workflows/instances/${instanceId}/approve`,
      payload
    );
    return data;
  }

  async rejectWorkflowStep(
    tenantId: string,
    instanceId: string,
    payload: { comment?: string }
  ): Promise<WorkflowInstance> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/workflows/instances/${instanceId}/reject`,
      payload
    );
    return data;
  }

  async seedWorkflowTemplates(tenantId: string): Promise<{ message: string }> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/workflows/templates/seed`);
    return data;
  }

  // Chat Token Metering (CAB-288)
  async getChatBudgetStatus(tenantId: string): Promise<TokenBudgetStatus> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/chat/usage/budget`);
    return data;
  }

  async getChatUsageStats(tenantId: string, days = 30): Promise<TokenUsageStats> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/chat/usage/metering`, {
      params: { days },
    });
    return data;
  }
}

// Operations metrics types (CAB-Observability)
export interface OperationsMetrics {
  error_rate: number;
  p95_latency_ms: number;
  requests_per_minute: number;
  active_alerts: number;
  uptime: number;
}

// Business metrics types (CAB-Observability)
export interface BusinessMetrics {
  active_tenants: number;
  new_tenants_30d: number;
  tenant_growth: number;
  apdex_score: number;
  total_tokens: number;
  total_calls: number;
}

export interface TopAPI {
  tool_name: string;
  display_name: string;
  calls: number;
}

// Chat Token Metering types (CAB-288)
export interface TokenBudgetStatus {
  user_tokens_today: number;
  tenant_tokens_today: number;
  daily_budget: number;
  remaining: number;
  budget_exceeded: boolean;
  usage_percent: number;
}

export interface TokenUsageStats {
  tenant_id: string;
  period_days: number;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_requests: number;
  today_tokens: number;
  top_users: { user_id: string; tokens: number }[];
  daily_breakdown: { date: string; tokens: number }[];
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
