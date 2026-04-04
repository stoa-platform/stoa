import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { config } from '../config';
import { getFriendlyErrorMessage } from '@stoa/shared/utils';
import type {
  Tenant,
  TenantCreate,
  API,
  APICreate,
  APIVersionEntry,
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
  AccessRequestListResponse,
  AdminUserListResponse,
  PlatformSettingsResponse,
  PlatformSetting,
  RoleListResponse,
  Subscription,
  SubscriptionListResponse,
  SubscriptionStats,
  BulkSubscriptionAction,
  BulkActionResult,
  TenantWebhook,
  WebhookCreate,
  WebhookUpdate,
  WebhookListResponse,
  WebhookDeliveryListResponse,
  WebhookTestResponse,
  CredentialMapping,
  CredentialMappingCreate,
  CredentialMappingUpdate,
  CredentialMappingListResponse,
  Contract,
  ContractCreate,
  ContractUpdate,
  ContractListResponse,
  PublishContractResponse,
  ProtocolBinding,
  Promotion,
  PromotionCreate,
  PromotionRollbackRequest,
  PromotionListResponse,
  PromotionDiffResponse,
  TenantCAInfo,
  CSRSignResponse,
  IssuedCertificateListResponse,
  TenantToolPermission,
  TenantToolPermissionCreate,
  TenantToolPermissionListResponse,
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
            // Token refresh returned null — session expired, reject queued requests
            this.refreshQueue.forEach(({ reject }) => reject(error));
            this.refreshQueue = [];
          } catch (refreshError) {
            this.refreshQueue.forEach(({ reject }) => reject(refreshError));
            this.refreshQueue = [];
            return Promise.reject(refreshError);
          } finally {
            this.isRefreshing = false;
          }
        }
        // CAB-1629: Replace raw HTTP status messages with user-friendly ones
        if (error instanceof Error) {
          error.message = getFriendlyErrorMessage(error, error.message);
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

  getAuthToken(): string | null {
    return this.authToken;
  }

  clearAuthToken() {
    this.authToken = null;
    delete this.client.defaults.headers.common['Authorization'];
  }

  // Generic HTTP methods for proxy services
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

  // User profile
  async getMe(): Promise<{
    roles: string[];
    permissions: string[];
    role_display_names?: Record<string, string>;
    tenant_id?: string;
  }> {
    const { data } = await this.client.get('/v1/me');
    return data;
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

  async getAdminApis(page = 1, pageSize = 100): Promise<API[]> {
    const { data } = await this.client.get('/v1/admin/catalog/apis', {
      params: { page, page_size: pageSize },
    });
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

  async getApiVersions(tenantId: string, apiId: string, limit = 20): Promise<APIVersionEntry[]> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/apis/${apiId}/versions`, {
      params: { limit },
    });
    return data;
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

  async triggerCatalogSync(tenantId: string): Promise<void> {
    await this.client.post(`/v1/admin/catalog/sync/tenant/${tenantId}`);
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
  async getConsumers(tenantId: string, environment?: string): Promise<Consumer[]> {
    const { data } = await this.client.get(`/v1/consumers/${tenantId}`, {
      params: { page: 1, page_size: 100, environment },
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

  // Tenant CA (CAB-1787/1788 — per-tenant CA management)
  async getTenantCA(tenantId: string): Promise<TenantCAInfo> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/ca`);
    return data;
  }

  async generateTenantCA(tenantId: string): Promise<TenantCAInfo> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/ca/generate`);
    return data;
  }

  async signCSR(
    tenantId: string,
    csrPem: string,
    validityDays: number = 365
  ): Promise<CSRSignResponse> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/ca/sign`, {
      csr_pem: csrPem,
      validity_days: validityDays,
    });
    return data;
  }

  async revokeTenantCA(tenantId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/ca`);
  }

  async listIssuedCertificates(
    tenantId: string,
    status?: string
  ): Promise<IssuedCertificateListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/ca/certificates`, {
      params: status ? { status } : undefined,
    });
    return data;
  }

  async revokeIssuedCertificate(tenantId: string, certId: string): Promise<void> {
    await this.client.post(`/v1/tenants/${tenantId}/ca/certificates/${certId}/revoke`);
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

  // ── Promotions (CAB-1706) ──────────────────────────────────────────────────

  async listPromotions(
    tenantId: string,
    params?: {
      api_id?: string;
      status?: string;
      target_environment?: string;
      page?: number;
      page_size?: number;
    }
  ): Promise<PromotionListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/promotions`, { params });
    return data;
  }

  async getPromotion(tenantId: string, promotionId: string): Promise<Promotion> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/promotions/${promotionId}`);
    return data;
  }

  async createPromotion(
    tenantId: string,
    apiId: string,
    request: PromotionCreate
  ): Promise<Promotion> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/promotions/${apiId}`, request);
    return data;
  }

  async approvePromotion(tenantId: string, promotionId: string): Promise<Promotion> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/promotions/${promotionId}/approve`
    );
    return data;
  }

  async completePromotion(tenantId: string, promotionId: string): Promise<Promotion> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/promotions/${promotionId}/complete`
    );
    return data;
  }

  async rollbackPromotion(
    tenantId: string,
    promotionId: string,
    request: PromotionRollbackRequest
  ): Promise<Promotion> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/promotions/${promotionId}/rollback`,
      request
    );
    return data;
  }

  async getPromotionDiff(tenantId: string, promotionId: string): Promise<PromotionDiffResponse> {
    const { data } = await this.client.get(
      `/v1/tenants/${tenantId}/promotions/${promotionId}/diff`
    );
    return data;
  }

  // ── Environment Status ────────────────────────────────────────────────────

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
    status?: string,
    environment?: string
  ): Promise<{ traces: TraceSummary[]; total: number }> {
    const params: Record<string, any> = {};
    if (limit) params.limit = limit;
    if (tenantId) params.tenant_id = tenantId;
    if (status) params.status = status;
    if (environment) params.environment = environment;
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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getAiSessionStats(days?: number, worker?: string): Promise<any> {
    const params: Record<string, string | number> = {};
    if (days) params.days = days;
    if (worker) params.worker = worker;
    const { data } = await this.client.get('/v1/traces/stats/ai-sessions', { params });
    return data;
  }

  async exportAiSessionsCsv(days?: number, worker?: string): Promise<Blob> {
    const params: Record<string, string | number> = {};
    if (days) params.days = days;
    if (worker) params.worker = worker;
    const { data } = await this.client.get('/v1/traces/export/ai-sessions', {
      params,
      responseType: 'blob',
    });
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

  // Admin Access Requests (CAB-1468)
  async getAccessRequests(params: {
    status?: string;
    page?: number;
    limit?: number;
  }): Promise<AccessRequestListResponse> {
    const { data } = await this.client.get('/v1/admin/access-requests', { params });
    return data;
  }

  // Gateway Instances (Control Plane Agnostique)
  async getGatewayInstances(params?: {
    gateway_type?: string;
    environment?: string;
    tenant_id?: string;
    include_deleted?: boolean;
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

  async getGatewayTools(id: string): Promise<any[]> {
    const { data } = await this.client.get(`/v1/admin/gateways/${id}/tools`);
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

  async restoreGatewayInstance(id: string): Promise<any> {
    const { data } = await this.client.post(`/v1/admin/gateways/${id}/restore`);
    return data;
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
    environment?: string;
    gateway_type?: string;
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

  async testDeployment(id: string): Promise<{
    reachable: boolean;
    status_code?: number;
    latency_ms?: number;
    error?: string;
    gateway_url?: string;
    path?: string;
  }> {
    const { data } = await this.client.post(`/v1/admin/deployments/${id}/test`);
    return data;
  }

  async getCatalogEntries(): Promise<
    { id: string; api_name: string; tenant_id: string; version: string }[]
  > {
    const { data } = await this.client.get('/v1/admin/deployments/catalog-entries');
    return data;
  }

  // API Deployment Orchestration (CAB-1888)

  async getDeployableEnvironments(
    tenantId: string,
    apiId: string
  ): Promise<{
    environments: {
      environment: string;
      deployable: boolean;
      promotion_status: string;
    }[];
  }> {
    const { data } = await this.client.get(
      `/v1/tenants/${tenantId}/apis/${apiId}/deployable-environments`
    );
    return data;
  }

  async deployApiToEnv(
    tenantId: string,
    apiId: string,
    payload: { environment: string; gateway_ids?: string[] }
  ): Promise<{ deployed: number; environment: string; deployment_ids: string[] }> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/apis/${apiId}/deploy`,
      payload
    );
    return data;
  }

  async getApiGatewayAssignments(
    tenantId: string,
    apiId: string,
    environment?: string
  ): Promise<{ items: any[]; total: number }> {
    const { data } = await this.client.get(
      `/v1/tenants/${tenantId}/apis/${apiId}/gateway-assignments`,
      { params: environment ? { environment } : {} }
    );
    return data;
  }

  async createApiGatewayAssignment(
    tenantId: string,
    apiId: string,
    payload: { gateway_id: string; environment: string; auto_deploy: boolean }
  ): Promise<any> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/apis/${apiId}/gateway-assignments`,
      payload
    );
    return data;
  }

  async deleteApiGatewayAssignment(
    tenantId: string,
    apiId: string,
    assignmentId: string
  ): Promise<void> {
    await this.client.delete(
      `/v1/tenants/${tenantId}/apis/${apiId}/gateway-assignments/${assignmentId}`
    );
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

  async getGatewayPolicies(params?: { tenant_id?: string; environment?: string }): Promise<any[]> {
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

  // Tool Permissions (CAB-1982)
  async listToolPermissions(
    tenantId: string,
    params?: { mcp_server_id?: string; page?: number; page_size?: number }
  ): Promise<TenantToolPermissionListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/tool-permissions`, {
      params: { ...params, page_size: params?.page_size ?? 100 },
    });
    return data;
  }

  async upsertToolPermission(
    tenantId: string,
    body: TenantToolPermissionCreate
  ): Promise<TenantToolPermission> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/tool-permissions`, body);
    return data;
  }

  async deleteToolPermission(tenantId: string, permissionId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/tool-permissions/${permissionId}`);
  }

  // Chat Settings (CAB-1852)
  async getChatSettings(tenantId: string): Promise<TenantChatSettings> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/chat/settings`);
    return data;
  }

  async updateChatSettings(
    tenantId: string,
    settings: Partial<TenantChatSettings>
  ): Promise<TenantChatSettings> {
    const { data } = await this.client.put(`/v1/tenants/${tenantId}/chat/settings`, settings);
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

  // Chat Usage by source — per-app breakdown (CAB-1868)
  async getChatUsageTenant(
    tenantId: string,
    params: { group_by?: string; days?: number } = {}
  ): Promise<ChatUsageBySource> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/chat/usage/tenant`, {
      params: { group_by: 'source', ...params },
    });
    return data;
  }

  // Chat conversation metrics — tenant-level aggregates (CAB-1868)
  async getChatConversationMetrics(tenantId: string): Promise<ChatConversationMetrics> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/chat/usage/tenant`);
    return data;
  }

  // Chat model distribution — conversations per model (CAB-1868)
  async getChatModelDistribution(tenantId: string): Promise<ChatModelDistribution> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/chat/usage/models`);
    return data;
  }

  async createChatConversation(
    tenantId: string,
    title = 'New conversation'
  ): Promise<{ id: string }> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/chat/conversations`, {
      title,
    });
    return data;
  }

  // =========================================================================
  // Admin Users Management (CAB-1454)
  // =========================================================================

  async getAdminUsers(params: {
    role?: string;
    status?: string;
    search?: string;
    page?: number;
    limit?: number;
  }): Promise<AdminUserListResponse> {
    const { data } = await this.client.get('/v1/admin/users', { params });
    return data;
  }

  // =========================================================================
  // Platform Settings (CAB-1454)
  // =========================================================================

  async getPlatformSettings(params?: { category?: string }): Promise<PlatformSettingsResponse> {
    const { data } = await this.client.get('/v1/admin/settings', { params });
    return data;
  }

  async updatePlatformSetting(key: string, value: string): Promise<PlatformSetting> {
    const { data } = await this.client.put(`/v1/admin/settings/${key}`, { value });
    return data;
  }

  // =========================================================================
  // RBAC Roles (CAB-1454)
  // =========================================================================

  async getAdminRoles(): Promise<RoleListResponse> {
    const { data } = await this.client.get('/v1/admin/roles');
    return data;
  }

  // =========================================================================
  // LLM Usage & Cost Monitoring (CAB-1487)
  // =========================================================================

  async getLlmUsage(
    tenantId: string,
    period: 'hour' | 'day' | 'week' | 'month' = 'month'
  ): Promise<LlmUsageResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/llm/usage`, {
      params: { period },
    });
    return data;
  }

  async getLlmTimeseries(
    tenantId: string,
    period: 'hour' | 'day' | 'week' | 'month' = 'week'
  ): Promise<LlmTimeseriesResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/llm/usage/timeseries`, {
      params: { period },
    });
    return data;
  }

  async getLlmProviderBreakdown(
    tenantId: string,
    period: 'hour' | 'day' | 'week' | 'month' = 'month'
  ): Promise<LlmProviderBreakdownResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/llm/usage/providers`, {
      params: { period },
    });
    return data;
  }

  async getLlmBudget(tenantId: string): Promise<LlmBudgetResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/llm/budget`);
    return data;
  }

  async updateLlmBudget(
    tenantId: string,
    update: { monthly_limit_usd?: number; alert_threshold_pct?: number }
  ): Promise<LlmBudgetResponse> {
    const { data } = await this.client.put(`/v1/tenants/${tenantId}/llm/budget`, update);
    return data;
  }

  // ============== Subscription Management (CAB-1635) ==============

  async getSubscriptions(
    tenantId: string,
    status?: string,
    page = 1,
    pageSize = 20,
    environment?: string
  ): Promise<SubscriptionListResponse> {
    const { data } = await this.client.get(`/v1/subscriptions/tenant/${tenantId}`, {
      params: { status, page, page_size: pageSize, environment },
    });
    return data;
  }

  async getPendingSubscriptions(
    tenantId: string,
    page = 1,
    pageSize = 20
  ): Promise<SubscriptionListResponse> {
    const { data } = await this.client.get(`/v1/subscriptions/tenant/${tenantId}/pending`, {
      params: { page, page_size: pageSize },
    });
    return data;
  }

  async getSubscriptionStats(tenantId: string): Promise<SubscriptionStats> {
    const { data } = await this.client.get(`/v1/subscriptions/tenant/${tenantId}/stats`);
    return data;
  }

  async approveSubscription(id: string, expiresAt?: string): Promise<Subscription> {
    const { data } = await this.client.post(`/v1/subscriptions/${id}/approve`, {
      expires_at: expiresAt || null,
    });
    return data;
  }

  async rejectSubscription(id: string, reason: string): Promise<Subscription> {
    const { data } = await this.client.post(`/v1/subscriptions/${id}/reject`, { reason });
    return data;
  }

  async bulkSubscriptionAction(payload: BulkSubscriptionAction): Promise<BulkActionResult> {
    const { data } = await this.client.post('/v1/subscriptions/bulk', payload);
    return data;
  }

  // ============ Webhook Management (CAB-1647) ============

  async getWebhooks(tenantId: string): Promise<WebhookListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/webhooks`);
    return data;
  }

  async getWebhook(tenantId: string, webhookId: string): Promise<TenantWebhook> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/webhooks/${webhookId}`);
    return data;
  }

  async createWebhook(tenantId: string, payload: WebhookCreate): Promise<TenantWebhook> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/webhooks`, payload);
    return data;
  }

  async updateWebhook(
    tenantId: string,
    webhookId: string,
    payload: WebhookUpdate
  ): Promise<TenantWebhook> {
    const { data } = await this.client.patch(
      `/v1/tenants/${tenantId}/webhooks/${webhookId}`,
      payload
    );
    return data;
  }

  async deleteWebhook(tenantId: string, webhookId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/webhooks/${webhookId}`);
  }

  async testWebhook(tenantId: string, webhookId: string): Promise<WebhookTestResponse> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/webhooks/${webhookId}/test`, {
      event_type: 'subscription.created',
    });
    return data;
  }

  async getWebhookDeliveries(
    tenantId: string,
    webhookId: string,
    limit = 50
  ): Promise<WebhookDeliveryListResponse> {
    const { data } = await this.client.get(
      `/v1/tenants/${tenantId}/webhooks/${webhookId}/deliveries`,
      { params: { limit } }
    );
    return data;
  }

  async retryWebhookDelivery(
    tenantId: string,
    webhookId: string,
    deliveryId: string
  ): Promise<void> {
    await this.client.post(
      `/v1/tenants/${tenantId}/webhooks/${webhookId}/deliveries/${deliveryId}/retry`
    );
  }

  // ============ Credential Mappings (CAB-1648) ============

  async getCredentialMappings(tenantId: string): Promise<CredentialMappingListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/credential-mappings`);
    return data;
  }

  async createCredentialMapping(
    tenantId: string,
    payload: CredentialMappingCreate
  ): Promise<CredentialMapping> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/credential-mappings`, payload);
    return data;
  }

  async updateCredentialMapping(
    tenantId: string,
    mappingId: string,
    payload: CredentialMappingUpdate
  ): Promise<CredentialMapping> {
    const { data } = await this.client.put(
      `/v1/tenants/${tenantId}/credential-mappings/${mappingId}`,
      payload
    );
    return data;
  }

  async deleteCredentialMapping(tenantId: string, mappingId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/credential-mappings/${mappingId}`);
  }

  // ============ Contracts / UAC (CAB-1649) ============

  async getContracts(tenantId: string): Promise<ContractListResponse> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/contracts`);
    return data;
  }

  async getContract(tenantId: string, contractId: string): Promise<Contract> {
    const { data } = await this.client.get(`/v1/tenants/${tenantId}/contracts/${contractId}`);
    return data;
  }

  async createContract(tenantId: string, payload: ContractCreate): Promise<Contract> {
    const { data } = await this.client.post(`/v1/tenants/${tenantId}/contracts`, payload);
    return data;
  }

  async publishContract(tenantId: string, contractId: string): Promise<PublishContractResponse> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/contracts/${contractId}/publish`
    );
    return data;
  }

  async updateContract(
    tenantId: string,
    contractId: string,
    payload: ContractUpdate
  ): Promise<Contract> {
    const { data } = await this.client.patch(
      `/v1/tenants/${tenantId}/contracts/${contractId}`,
      payload
    );
    return data;
  }

  async deleteContract(tenantId: string, contractId: string): Promise<void> {
    await this.client.delete(`/v1/tenants/${tenantId}/contracts/${contractId}`);
  }

  async getContractBindings(tenantId: string, contractId: string): Promise<ProtocolBinding[]> {
    const { data } = await this.client.get(
      `/v1/tenants/${tenantId}/contracts/${contractId}/bindings`
    );
    return data;
  }

  async enableBinding(
    tenantId: string,
    contractId: string,
    protocol: string
  ): Promise<ProtocolBinding> {
    const { data } = await this.client.post(
      `/v1/tenants/${tenantId}/contracts/${contractId}/bindings`,
      { protocol }
    );
    return data;
  }

  async disableBinding(tenantId: string, contractId: string, protocol: string): Promise<void> {
    await this.client.delete(
      `/v1/tenants/${tenantId}/contracts/${contractId}/bindings/${protocol}`
    );
  }

  // ============ Monitoring / Call Flow (CAB-1869) ============

  async getTransactions(
    limit = 20,
    status?: string,
    timeRange?: string
  ): Promise<{ transactions: MonitoringTransaction[] }> {
    const params: Record<string, string | number> = { limit };
    if (status) params.status = status;
    if (timeRange) params.time_range = timeRange;
    const { data } = await this.client.get('/v1/monitoring/transactions', { params });
    return data;
  }

  async getTransactionDetail(transactionId: string): Promise<MonitoringTransactionDetail> {
    const { data } = await this.client.get(`/v1/monitoring/transactions/${transactionId}`);
    return data;
  }

  async getTransactionStats(timeRange?: string): Promise<MonitoringStats> {
    const params: Record<string, string> = {};
    if (timeRange) params.time_range = timeRange;
    const { data } = await this.client.get('/v1/monitoring/transactions/stats', { params });
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

// Chat Settings types (CAB-1852)
export interface TenantChatSettings {
  chat_console_enabled: boolean;
  chat_portal_enabled: boolean;
  chat_daily_budget: number;
}

// Chat Usage by source — per-app breakdown (CAB-1868)
export interface ChatSourceEntry {
  source: string;
  tokens: number;
  requests: number;
}

export interface ChatUsageBySource {
  sources: ChatSourceEntry[];
  total_tokens: number;
  total_requests: number;
  period_days: number;
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

// Chat conversation metrics (CAB-1868)
export interface ChatConversationMetrics {
  tenant_id: string;
  total_conversations: number;
  total_messages: number;
  total_tokens: number;
  unique_users: number;
}

export interface ModelDistributionEntry {
  model: string;
  conversations: number;
}

export interface ChatModelDistribution {
  models: ModelDistributionEntry[];
  total_conversations: number;
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

// LLM Usage & Cost types (CAB-1487)
export interface LlmUsageResponse {
  total_cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  avg_cost_per_request: number;
  cache_read_cost_usd: number;
  cache_write_cost_usd: number;
  period: string;
}

export interface LlmTimeseriesPoint {
  timestamp: string;
  value: number;
}

export interface LlmTimeseriesResponse {
  points: LlmTimeseriesPoint[];
  period: string;
  step: string;
}

export interface LlmProviderCostEntry {
  provider: string;
  model: string;
  cost_usd: number;
}

export interface LlmProviderBreakdownResponse {
  providers: LlmProviderCostEntry[];
  period: string;
}

export interface LlmBudgetResponse {
  id: string;
  tenant_id: string;
  monthly_limit_usd: number;
  current_spend_usd: number;
  remaining_usd: number;
  usage_pct: number;
  alert_threshold_pct: number;
  is_over_budget: boolean;
}

// ─── Monitoring / Call Flow ───

export interface MonitoringTransaction {
  id: string;
  trace_id: string;
  api_name: string;
  method: string;
  path: string;
  status_code: number;
  status: string;
  status_text: string;
  error_source: string | null;
  started_at: string;
  total_duration_ms: number;
  spans_count: number;
}

export interface MonitoringTransactionDetail extends MonitoringTransaction {
  tenant_id: string | null;
  client_ip: string | null;
  user_id: string | null;
  spans: Array<{
    name: string;
    service: string;
    start_offset_ms: number;
    duration_ms: number;
    status: string;
    metadata: Record<string, unknown>;
  }>;
  request_headers: Record<string, string> | null;
  response_headers: Record<string, string> | null;
  error_message: string | null;
  demo_mode: boolean;
}

export interface MonitoringStats {
  total_requests: number;
  success_count: number;
  error_count: number;
  timeout_count: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  requests_per_minute: number;
  by_api: Record<string, number>;
  by_status_code: Record<string, number>;
}

export const apiService = new ApiService();
