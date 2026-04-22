import type {
  Tenant,
  TenantCreate,
  API,
  APICreate,
  Application,
  ApplicationCreate,
  Consumer,
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
  TenantWebhook,
  WebhookListResponse,
  WebhookDeliveryListResponse,
  CredentialMapping,
  CredentialMappingListResponse,
  Contract,
  ContractCreate,
  ContractListResponse,
  PublishContractResponse,
  ProtocolBinding,
  Promotion,
  PromotionListResponse,
  TenantCAInfo,
  IssuedCertificateListResponse,
  TenantToolPermission,
  TenantToolPermissionListResponse,
} from '../types';
import type { Schemas } from '@stoa/shared/api-types';
import {
  httpClient,
  setAuthToken as setAuthTokenCore,
  getAuthToken as getAuthTokenCore,
  clearAuthToken as clearAuthTokenCore,
  setTokenRefresher as setTokenRefresherCore,
  createEventSource as createEventSourceCore,
  type TokenRefresher,
} from './http';
import { gitClient } from './api/git';
import { sessionClient } from './api/session';
import { adminClient } from './api/admin';
import { toolPermissionsClient } from './api/toolPermissions';
import { workflowsClient } from './api/workflows';
import { subscriptionsClient } from './api/subscriptions';
import { webhooksClient } from './api/webhooks';
import { credentialMappingsClient } from './api/credentialMappings';
import { contractsClient } from './api/contracts';
import { promotionsClient } from './api/promotions';
import { tenantsClient } from './api/tenants';
import { apisClient } from './api/apis';
import { applicationsClient } from './api/applications';
import { consumersClient } from './api/consumers';

// =============================================================================
// Façade ApiService — agrège le core transport (services/http) et les méthodes
// métier historiques. En cours de refactor UI-2 : les domaines seront extraits
// en `services/api/<domain>.ts`. Cette classe reste le point d'entrée legacy
// pour préserver la surface consommée par ~76 callers et 56 vi.mock.
// =============================================================================
class ApiService {
  // Generic HTTP methods for proxy services (58 callers + 11 sibling services)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async get<T = any>(url: string, config?: { params?: Record<string, any> }): Promise<{ data: T }> {
    return httpClient.get<T>(url, config);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async post<T = any>(url: string, data?: any): Promise<{ data: T }> {
    return httpClient.post<T>(url, data);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async put<T = any>(url: string, data?: any): Promise<{ data: T }> {
    return httpClient.put<T>(url, data);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async patch<T = any>(url: string, data?: any): Promise<{ data: T }> {
    return httpClient.patch<T>(url, data);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async delete<T = any>(url: string): Promise<{ data: T }> {
    return httpClient.delete<T>(url);
  }

  // Auth plumbing — délègue à services/http
  setTokenRefresher(refresher: TokenRefresher): void {
    setTokenRefresherCore(refresher);
  }

  setAuthToken(token: string): void {
    setAuthTokenCore(token);
    httpClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  getAuthToken(): string | null {
    return getAuthTokenCore();
  }

  clearAuthToken(): void {
    clearAuthTokenCore();
    delete httpClient.defaults.headers.common['Authorization'];
  }

  // User profile
  async getMe(): Promise<{
    roles: string[];
    permissions: string[];
    role_display_names?: Record<string, string>;
    tenant_id?: string;
  }> {
    return sessionClient.getMe();
  }

  // Tenants
  async getTenants(): Promise<Tenant[]> {
    return tenantsClient.list();
  }

  async getTenant(tenantId: string): Promise<Tenant> {
    return tenantsClient.get(tenantId);
  }

  async createTenant(tenant: TenantCreate): Promise<Tenant> {
    return tenantsClient.create(tenant);
  }

  async updateTenant(tenantId: string, tenant: Partial<TenantCreate>): Promise<Tenant> {
    return tenantsClient.update(tenantId, tenant);
  }

  async deleteTenant(tenantId: string): Promise<void> {
    return tenantsClient.remove(tenantId);
  }

  // Environments (ADR-040)
  async getEnvironments(): Promise<EnvironmentConfig[]> {
    return sessionClient.listEnvironments();
  }

  // APIs
  async getApis(tenantId: string, environment?: Environment): Promise<API[]> {
    return apisClient.list(tenantId, environment);
  }

  async getAdminApis(page = 1, pageSize = 100): Promise<API[]> {
    return apisClient.listAdmin(page, pageSize);
  }

  async getApi(tenantId: string, apiId: string): Promise<API> {
    return apisClient.get(tenantId, apiId);
  }

  async createApi(tenantId: string, api: APICreate): Promise<API> {
    return apisClient.create(tenantId, api);
  }

  async updateApi(tenantId: string, apiId: string, api: Partial<APICreate>): Promise<API> {
    return apisClient.update(tenantId, apiId, api);
  }

  async deleteApi(tenantId: string, apiId: string): Promise<void> {
    return apisClient.remove(tenantId, apiId);
  }

  async getApiVersions(
    tenantId: string,
    apiId: string,
    limit = 20
  ): Promise<Schemas['APIVersionEntry'][]> {
    return apisClient.listVersions(tenantId, apiId, limit);
  }

  async updateApiAudience(
    tenantId: string,
    apiId: string,
    audience: string
  ): Promise<{ api_id: string; tenant_id: string; audience: string; updated_by: string }> {
    return apisClient.updateAudience(tenantId, apiId, audience);
  }

  async triggerCatalogSync(tenantId: string): Promise<void> {
    return apisClient.triggerCatalogSync(tenantId);
  }

  // Applications
  async getApplications(tenantId: string): Promise<Application[]> {
    return applicationsClient.list(tenantId);
  }

  async getApplication(tenantId: string, appId: string): Promise<Application> {
    return applicationsClient.get(tenantId, appId);
  }

  async createApplication(tenantId: string, app: ApplicationCreate): Promise<Application> {
    return applicationsClient.create(tenantId, app);
  }

  async updateApplication(
    tenantId: string,
    appId: string,
    app: Partial<ApplicationCreate>
  ): Promise<Application> {
    return applicationsClient.update(tenantId, appId, app);
  }

  async deleteApplication(tenantId: string, appId: string): Promise<void> {
    return applicationsClient.remove(tenantId, appId);
  }

  // Consumers (CAB-864 — mTLS Self-Service)
  async getConsumers(tenantId: string, environment?: string): Promise<Consumer[]> {
    return consumersClient.list(tenantId, environment);
  }

  async getConsumer(tenantId: string, consumerId: string): Promise<Consumer> {
    return consumersClient.get(tenantId, consumerId);
  }

  async suspendConsumer(tenantId: string, consumerId: string): Promise<Consumer> {
    return consumersClient.suspend(tenantId, consumerId);
  }

  async activateConsumer(tenantId: string, consumerId: string): Promise<Consumer> {
    return consumersClient.activate(tenantId, consumerId);
  }

  async deleteConsumer(tenantId: string, consumerId: string): Promise<void> {
    return consumersClient.remove(tenantId, consumerId);
  }

  async rotateCertificate(
    tenantId: string,
    consumerId: string,
    certificatePem: string,
    gracePeriodHours: number = 24
  ): Promise<Consumer> {
    return consumersClient.rotateCertificate(
      tenantId,
      consumerId,
      certificatePem,
      gracePeriodHours
    );
  }

  async revokeCertificate(tenantId: string, consumerId: string): Promise<Consumer> {
    return consumersClient.revokeCertificate(tenantId, consumerId);
  }

  async blockConsumer(tenantId: string, consumerId: string): Promise<Consumer> {
    return consumersClient.block(tenantId, consumerId);
  }

  // Certificate Lifecycle (CAB-872)
  async bindCertificate(
    tenantId: string,
    consumerId: string,
    certificatePem: string
  ): Promise<Consumer> {
    return consumersClient.bindCertificate(tenantId, consumerId, certificatePem);
  }

  async getExpiringCertificates(
    tenantId: string,
    days: number = 30
  ): Promise<Schemas['CertificateExpiryResponse']> {
    return consumersClient.getExpiringCertificates(tenantId, days);
  }

  async bulkRevokeCertificates(
    tenantId: string,
    consumerIds: string[]
  ): Promise<Schemas['BulkRevokeResponse']> {
    return consumersClient.bulkRevokeCertificates(tenantId, consumerIds);
  }

  // Tenant CA (CAB-1787/1788 — per-tenant CA management)
  async getTenantCA(tenantId: string): Promise<TenantCAInfo> {
    return tenantsClient.getCA(tenantId);
  }

  async generateTenantCA(tenantId: string): Promise<TenantCAInfo> {
    return tenantsClient.generateCA(tenantId);
  }

  async signCSR(
    tenantId: string,
    csrPem: string,
    validityDays: number = 365
  ): Promise<Schemas['CSRSignResponse']> {
    return tenantsClient.signCSR(tenantId, csrPem, validityDays);
  }

  async revokeTenantCA(tenantId: string): Promise<void> {
    return tenantsClient.revokeCA(tenantId);
  }

  async listIssuedCertificates(
    tenantId: string,
    status?: string
  ): Promise<IssuedCertificateListResponse> {
    return tenantsClient.listIssuedCertificates(tenantId, status);
  }

  async revokeIssuedCertificate(tenantId: string, certId: string): Promise<void> {
    return tenantsClient.revokeIssuedCertificate(tenantId, certId);
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
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/deployments`, { params });
    return data;
  }

  async getDeployment(tenantId: string, deploymentId: string): Promise<Deployment> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/deployments/${deploymentId}`);
    return data;
  }

  async createDeployment(tenantId: string, request: DeploymentCreate): Promise<Deployment> {
    const { data } = await httpClient.post(`/v1/tenants/${tenantId}/deployments`, request);
    return data;
  }

  async rollbackDeployment(
    tenantId: string,
    deploymentId: string,
    targetVersion?: string
  ): Promise<Deployment> {
    const { data } = await httpClient.post(
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
    const { data } = await httpClient.get(
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
    return promotionsClient.list(tenantId, params);
  }

  async getPromotion(tenantId: string, promotionId: string): Promise<Promotion> {
    return promotionsClient.get(tenantId, promotionId);
  }

  async createPromotion(
    tenantId: string,
    apiId: string,
    request: Schemas['PromotionCreate']
  ): Promise<Promotion> {
    return promotionsClient.create(tenantId, apiId, request);
  }

  async approvePromotion(tenantId: string, promotionId: string): Promise<Promotion> {
    return promotionsClient.approve(tenantId, promotionId);
  }

  async completePromotion(tenantId: string, promotionId: string): Promise<Promotion> {
    return promotionsClient.complete(tenantId, promotionId);
  }

  async rollbackPromotion(
    tenantId: string,
    promotionId: string,
    request: Schemas['PromotionRollbackRequest']
  ): Promise<Promotion> {
    return promotionsClient.rollback(tenantId, promotionId, request);
  }

  async getPromotionDiff(
    tenantId: string,
    promotionId: string
  ): Promise<Schemas['PromotionDiffResponse']> {
    return promotionsClient.getDiff(tenantId, promotionId);
  }

  // ── Environment Status ────────────────────────────────────────────────────

  async getEnvironmentStatus(
    tenantId: string,
    environment: string
  ): Promise<EnvironmentStatusResponse> {
    const { data } = await httpClient.get(
      `/v1/tenants/${tenantId}/deployments/environments/${environment}/status`
    );
    return data;
  }

  // Git
  async getCommits(tenantId: string, path?: string): Promise<CommitInfo[]> {
    return gitClient.listCommits(tenantId, path);
  }

  async getMergeRequests(tenantId: string): Promise<MergeRequest[]> {
    return gitClient.listMergeRequests(tenantId);
  }

  // SSE Events — délègue au helper du core transport
  createEventSource(tenantId: string, eventTypes?: string[]): EventSource {
    return createEventSourceCore(tenantId, eventTypes);
  }

  // Pipeline Traces
  async getTraces(
    limit?: number,
    tenantId?: string,
    status?: string,
    environment?: string
  ): Promise<{ traces: TraceSummary[]; total: number }> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const params: Record<string, any> = {};
    if (limit) params.limit = limit;
    if (tenantId) params.tenant_id = tenantId;
    if (status) params.status = status;
    if (environment) params.environment = environment;
    const { data } = await httpClient.get('/v1/traces', { params });
    return data;
  }

  async getTrace(traceId: string): Promise<PipelineTrace> {
    const { data } = await httpClient.get(`/v1/traces/${traceId}`);
    return data;
  }

  async getTraceTimeline(traceId: string): Promise<TraceTimeline> {
    const { data } = await httpClient.get(`/v1/traces/${traceId}/timeline`);
    return data;
  }

  async getTraceStats(): Promise<TraceStats> {
    const { data } = await httpClient.get('/v1/traces/stats');
    return data;
  }

  async getLiveTraces(): Promise<{ traces: PipelineTrace[]; count: number }> {
    const { data } = await httpClient.get('/v1/traces/live');
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getAiSessionStats(days?: number, worker?: string): Promise<any> {
    const params: Record<string, string | number> = {};
    if (days) params.days = days;
    if (worker) params.worker = worker;
    const { data } = await httpClient.get('/v1/traces/stats/ai-sessions', { params });
    return data;
  }

  async exportAiSessionsCsv(days?: number, worker?: string): Promise<Blob> {
    const params: Record<string, string | number> = {};
    if (days) params.days = days;
    if (worker) params.worker = worker;
    const { data } = await httpClient.get('/v1/traces/export/ai-sessions', {
      params,
      responseType: 'blob',
    });
    return data;
  }

  // Platform Status (CAB-654)
  async getPlatformStatus(): Promise<PlatformStatusResponse> {
    const { data } = await httpClient.get('/v1/platform/status');
    return data;
  }

  async getPlatformComponents(): Promise<ComponentStatus[]> {
    const { data } = await httpClient.get('/v1/platform/components');
    return data;
  }

  async getComponentStatus(name: string): Promise<ComponentStatus> {
    const { data } = await httpClient.get(`/v1/platform/components/${name}`);
    return data;
  }

  async syncPlatformComponent(name: string): Promise<{ message: string; operation: string }> {
    const { data } = await httpClient.post(`/v1/platform/components/${name}/sync`);
    return data;
  }

  async getComponentDiff(name: string): Promise<ApplicationDiffResponse> {
    const { data } = await httpClient.get(`/v1/platform/components/${name}/diff`);
    return data;
  }

  async getPlatformEvents(component?: string, limit?: number): Promise<PlatformEvent[]> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const params: Record<string, any> = {};
    if (component) params.component = component;
    if (limit) params.limit = limit;
    const { data } = await httpClient.get('/v1/platform/events', { params });
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
    return adminClient.listProspects(params);
  }

  async getProspectsMetrics(params?: {
    date_from?: string;
    date_to?: string;
  }): Promise<ProspectsMetricsResponse> {
    return adminClient.getProspectsMetrics(params);
  }

  async getProspect(inviteId: string): Promise<ProspectDetail> {
    return adminClient.getProspect(inviteId);
  }

  async exportProspectsCSV(params?: {
    company?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<Blob> {
    return adminClient.exportProspectsCSV(params);
  }

  // Admin Access Requests (CAB-1468)
  async getAccessRequests(params: {
    status?: string;
    page?: number;
    limit?: number;
  }): Promise<AccessRequestListResponse> {
    return adminClient.listAccessRequests(params);
  }

  // Gateway Instances (Control Plane Agnostique)
  async getGatewayInstances(params?: {
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
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGatewayInstance(id: string): Promise<any> {
    const { data } = await httpClient.get(`/v1/admin/gateways/${id}`);
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGatewayTools(id: string): Promise<any[]> {
    const { data } = await httpClient.get(`/v1/admin/gateways/${id}/tools`);
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async createGatewayInstance(payload: any): Promise<any> {
    const { data } = await httpClient.post('/v1/admin/gateways', payload);
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateGatewayInstance(id: string, payload: any): Promise<any> {
    const { data } = await httpClient.put(`/v1/admin/gateways/${id}`, payload);
    return data;
  }

  async deleteGatewayInstance(id: string): Promise<void> {
    await httpClient.delete(`/v1/admin/gateways/${id}`);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async restoreGatewayInstance(id: string): Promise<any> {
    const { data } = await httpClient.post(`/v1/admin/gateways/${id}/restore`);
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async checkGatewayHealth(id: string): Promise<any> {
    const { data } = await httpClient.post(`/v1/admin/gateways/${id}/health`);
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
    const { data } = await httpClient.get('/v1/admin/gateways/modes/stats');
    return data;
  }

  // Gateway Deployments
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getDeploymentStatusSummary(): Promise<any> {
    const { data } = await httpClient.get('/v1/admin/deployments/status');
    return data;
  }

  async getGatewayDeployments(params?: {
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
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGatewayDeployment(id: string): Promise<any> {
    const { data } = await httpClient.get(`/v1/admin/deployments/${id}`);
    return data;
  }

  async deployApiToGateways(payload: {
    api_catalog_id: string;
    gateway_instance_ids: string[];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  }): Promise<any[]> {
    const { data } = await httpClient.post('/v1/admin/deployments', payload);
    return data;
  }

  async undeployFromGateway(id: string): Promise<void> {
    await httpClient.delete(`/v1/admin/deployments/${id}`);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async forceSyncDeployment(id: string): Promise<any> {
    const { data } = await httpClient.post(`/v1/admin/deployments/${id}/sync`);
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
    const { data } = await httpClient.post(`/v1/admin/deployments/${id}/test`);
    return data;
  }

  async getCatalogEntries(): Promise<
    { id: string; api_name: string; tenant_id: string; version: string }[]
  > {
    const { data } = await httpClient.get('/v1/admin/deployments/catalog-entries');
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
    const { data } = await httpClient.get(
      `/v1/tenants/${tenantId}/apis/${apiId}/deployable-environments`
    );
    return data;
  }

  async deployApiToEnv(
    tenantId: string,
    apiId: string,
    payload: { environment: string; gateway_ids?: string[] }
  ): Promise<{ deployed: number; environment: string; deployment_ids: string[] }> {
    const { data } = await httpClient.post(`/v1/tenants/${tenantId}/apis/${apiId}/deploy`, payload);
    return data;
  }

  async getApiGatewayAssignments(
    tenantId: string,
    apiId: string,
    environment?: string
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ): Promise<{ items: any[]; total: number }> {
    const { data } = await httpClient.get(
      `/v1/tenants/${tenantId}/apis/${apiId}/gateway-assignments`,
      { params: environment ? { environment } : {} }
    );
    return data;
  }

  async createApiGatewayAssignment(
    tenantId: string,
    apiId: string,
    payload: { gateway_id: string; environment: string; auto_deploy: boolean }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ): Promise<any> {
    const { data } = await httpClient.post(
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
    await httpClient.delete(
      `/v1/tenants/${tenantId}/apis/${apiId}/gateway-assignments/${assignmentId}`
    );
  }

  // =========================================================================
  // Gateway Observability
  // =========================================================================

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGatewayAggregatedMetrics(): Promise<any> {
    const { data } = await httpClient.get('/v1/admin/gateways/metrics');
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGuardrailsEvents(limit = 20): Promise<any> {
    const { data } = await httpClient.get(
      `/v1/admin/gateways/metrics/guardrails/events?limit=${limit}`
    );
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGatewayHealthSummary(): Promise<any> {
    const { data } = await httpClient.get('/v1/admin/gateways/health-summary');
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGatewayInstanceMetrics(id: string): Promise<any> {
    const { data } = await httpClient.get(`/v1/admin/gateways/${id}/metrics`);
    return data;
  }

  // =========================================================================
  // Gateway Policies
  // =========================================================================

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getGatewayPolicies(params?: { tenant_id?: string; environment?: string }): Promise<any[]> {
    const { data } = await httpClient.get('/v1/admin/policies', { params });
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async createGatewayPolicy(payload: any): Promise<any> {
    const { data } = await httpClient.post('/v1/admin/policies', payload);
    return data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateGatewayPolicy(id: string, payload: any): Promise<any> {
    const { data } = await httpClient.put(`/v1/admin/policies/${id}`, payload);
    return data;
  }

  async deleteGatewayPolicy(id: string): Promise<void> {
    await httpClient.delete(`/v1/admin/policies/${id}`);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async createPolicyBinding(payload: any): Promise<any> {
    const { data } = await httpClient.post('/v1/admin/policies/bindings', payload);
    return data;
  }

  async deletePolicyBinding(id: string): Promise<void> {
    await httpClient.delete(`/v1/admin/policies/bindings/${id}`);
  }

  // =========================================================================
  // Operations Dashboard (CAB-Observability)
  // =========================================================================

  async getOperationsMetrics(): Promise<OperationsMetrics> {
    const { data } = await httpClient.get('/v1/operations/metrics');
    return data;
  }

  // =========================================================================
  // Business Analytics (CAB-Observability)
  // =========================================================================

  async getBusinessMetrics(): Promise<BusinessMetrics> {
    const { data } = await httpClient.get('/v1/business/metrics');
    return data;
  }

  async getTopAPIs(limit = 10): Promise<TopAPI[]> {
    const { data } = await httpClient.get(`/v1/business/top-apis?limit=${limit}`);
    return data;
  }

  // Workflow Engine methods (CAB-593)
  async listWorkflowTemplates(tenantId: string): Promise<WorkflowTemplateListResponse> {
    return workflowsClient.listTemplates(tenantId);
  }

  async createWorkflowTemplate(
    tenantId: string,
    payload: WorkflowTemplateCreate
  ): Promise<WorkflowTemplate> {
    return workflowsClient.createTemplate(tenantId, payload);
  }

  async updateWorkflowTemplate(
    tenantId: string,
    templateId: string,
    payload: WorkflowTemplateUpdate
  ): Promise<WorkflowTemplate> {
    return workflowsClient.updateTemplate(tenantId, templateId, payload);
  }

  async deleteWorkflowTemplate(tenantId: string, templateId: string): Promise<void> {
    return workflowsClient.deleteTemplate(tenantId, templateId);
  }

  async listWorkflowInstances(
    tenantId: string,
    params?: { status?: string; skip?: number; limit?: number }
  ): Promise<WorkflowListResponse> {
    return workflowsClient.listInstances(tenantId, params);
  }

  async startWorkflow(
    tenantId: string,
    payload: { template_id: string; subject_id: string; subject_email: string }
  ): Promise<WorkflowInstance> {
    return workflowsClient.start(tenantId, payload);
  }

  async approveWorkflowStep(
    tenantId: string,
    instanceId: string,
    payload: { comment?: string }
  ): Promise<WorkflowInstance> {
    return workflowsClient.approveStep(tenantId, instanceId, payload);
  }

  async rejectWorkflowStep(
    tenantId: string,
    instanceId: string,
    payload: { comment?: string }
  ): Promise<WorkflowInstance> {
    return workflowsClient.rejectStep(tenantId, instanceId, payload);
  }

  async seedWorkflowTemplates(tenantId: string): Promise<{ message: string }> {
    return workflowsClient.seedTemplates(tenantId);
  }

  // Tool Permissions (CAB-1982)
  async listToolPermissions(
    tenantId: string,
    params?: { mcp_server_id?: string; page?: number; page_size?: number }
  ): Promise<TenantToolPermissionListResponse> {
    return toolPermissionsClient.list(tenantId, params);
  }

  async upsertToolPermission(
    tenantId: string,
    body: Schemas['TenantToolPermissionCreate']
  ): Promise<TenantToolPermission> {
    return toolPermissionsClient.upsert(tenantId, body);
  }

  async deleteToolPermission(tenantId: string, permissionId: string): Promise<void> {
    return toolPermissionsClient.remove(tenantId, permissionId);
  }

  // Chat Settings (CAB-1852)
  async getChatSettings(tenantId: string): Promise<TenantChatSettings> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/chat/settings`);
    return data;
  }

  async updateChatSettings(
    tenantId: string,
    settings: Partial<TenantChatSettings>
  ): Promise<TenantChatSettings> {
    const { data } = await httpClient.put(`/v1/tenants/${tenantId}/chat/settings`, settings);
    return data;
  }

  // Chat Token Metering (CAB-288)
  async getChatBudgetStatus(tenantId: string): Promise<TokenBudgetStatus> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/chat/usage/budget`);
    return data;
  }

  async getChatUsageStats(tenantId: string, days = 30): Promise<TokenUsageStats> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/chat/usage/metering`, {
      params: { days },
    });
    return data;
  }

  // Chat Usage by source — per-app breakdown (CAB-1868)
  async getChatUsageTenant(
    tenantId: string,
    params: { group_by?: string; days?: number } = {}
  ): Promise<ChatUsageBySource> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/chat/usage/tenant`, {
      params: { group_by: 'source', ...params },
    });
    return data;
  }

  // Chat conversation metrics — tenant-level aggregates (CAB-1868)
  async getChatConversationMetrics(tenantId: string): Promise<ChatConversationMetrics> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/chat/usage/tenant`);
    return data;
  }

  // Chat model distribution — conversations per model (CAB-1868)
  async getChatModelDistribution(tenantId: string): Promise<ChatModelDistribution> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/chat/usage/models`);
    return data;
  }

  async createChatConversation(
    tenantId: string,
    title = 'New conversation'
  ): Promise<{ id: string }> {
    const { data } = await httpClient.post(`/v1/tenants/${tenantId}/chat/conversations`, {
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
    return adminClient.listUsers(params);
  }

  // =========================================================================
  // Platform Settings (CAB-1454)
  // =========================================================================

  async getPlatformSettings(params?: { category?: string }): Promise<PlatformSettingsResponse> {
    return adminClient.listSettings(params);
  }

  async updatePlatformSetting(key: string, value: string): Promise<PlatformSetting> {
    return adminClient.updateSetting(key, value);
  }

  // =========================================================================
  // RBAC Roles (CAB-1454)
  // =========================================================================

  async getAdminRoles(): Promise<RoleListResponse> {
    return adminClient.listRoles();
  }

  // =========================================================================
  // LLM Usage & Cost Monitoring (CAB-1487)
  // =========================================================================

  async getLlmUsage(
    tenantId: string,
    period: 'hour' | 'day' | 'week' | 'month' = 'month'
  ): Promise<LlmUsageResponse> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/llm/usage`, {
      params: { period },
    });
    return data;
  }

  async getLlmTimeseries(
    tenantId: string,
    period: 'hour' | 'day' | 'week' | 'month' = 'week'
  ): Promise<LlmTimeseriesResponse> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/llm/usage/timeseries`, {
      params: { period },
    });
    return data;
  }

  async getLlmProviderBreakdown(
    tenantId: string,
    period: 'hour' | 'day' | 'week' | 'month' = 'month'
  ): Promise<LlmProviderBreakdownResponse> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/llm/usage/providers`, {
      params: { period },
    });
    return data;
  }

  async getLlmBudget(tenantId: string): Promise<LlmBudgetResponse> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/llm/budget`);
    return data;
  }

  async updateLlmBudget(
    tenantId: string,
    update: { monthly_limit_usd?: number; alert_threshold_pct?: number }
  ): Promise<LlmBudgetResponse> {
    const { data } = await httpClient.put(`/v1/tenants/${tenantId}/llm/budget`, update);
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
    return subscriptionsClient.list(tenantId, status, page, pageSize, environment);
  }

  async getPendingSubscriptions(
    tenantId: string,
    page = 1,
    pageSize = 20
  ): Promise<SubscriptionListResponse> {
    return subscriptionsClient.listPending(tenantId, page, pageSize);
  }

  async getSubscriptionStats(tenantId: string): Promise<SubscriptionStats> {
    return subscriptionsClient.getStats(tenantId);
  }

  async approveSubscription(id: string, expiresAt?: string): Promise<Subscription> {
    return subscriptionsClient.approve(id, expiresAt);
  }

  async rejectSubscription(id: string, reason: string): Promise<Subscription> {
    return subscriptionsClient.reject(id, reason);
  }

  async bulkSubscriptionAction(
    payload: Schemas['BulkSubscriptionAction']
  ): Promise<Schemas['BulkActionResult']> {
    return subscriptionsClient.bulkAction(payload);
  }

  // ============ Webhook Management (CAB-1647) ============

  async getWebhooks(tenantId: string): Promise<WebhookListResponse> {
    return webhooksClient.list(tenantId);
  }

  async getWebhook(tenantId: string, webhookId: string): Promise<TenantWebhook> {
    return webhooksClient.get(tenantId, webhookId);
  }

  async createWebhook(tenantId: string, payload: Schemas['WebhookCreate']): Promise<TenantWebhook> {
    return webhooksClient.create(tenantId, payload);
  }

  async updateWebhook(
    tenantId: string,
    webhookId: string,
    payload: Schemas['WebhookUpdate']
  ): Promise<TenantWebhook> {
    return webhooksClient.update(tenantId, webhookId, payload);
  }

  async deleteWebhook(tenantId: string, webhookId: string): Promise<void> {
    return webhooksClient.remove(tenantId, webhookId);
  }

  async testWebhook(tenantId: string, webhookId: string): Promise<Schemas['WebhookTestResponse']> {
    return webhooksClient.test(tenantId, webhookId);
  }

  async getWebhookDeliveries(
    tenantId: string,
    webhookId: string,
    limit = 50
  ): Promise<WebhookDeliveryListResponse> {
    return webhooksClient.listDeliveries(tenantId, webhookId, limit);
  }

  async retryWebhookDelivery(
    tenantId: string,
    webhookId: string,
    deliveryId: string
  ): Promise<void> {
    return webhooksClient.retryDelivery(tenantId, webhookId, deliveryId);
  }

  // ============ Credential Mappings (CAB-1648) ============

  async getCredentialMappings(tenantId: string): Promise<CredentialMappingListResponse> {
    return credentialMappingsClient.list(tenantId);
  }

  async createCredentialMapping(
    tenantId: string,
    payload: Schemas['CredentialMappingCreate']
  ): Promise<CredentialMapping> {
    return credentialMappingsClient.create(tenantId, payload);
  }

  async updateCredentialMapping(
    tenantId: string,
    mappingId: string,
    payload: Schemas['CredentialMappingUpdate']
  ): Promise<CredentialMapping> {
    return credentialMappingsClient.update(tenantId, mappingId, payload);
  }

  async deleteCredentialMapping(tenantId: string, mappingId: string): Promise<void> {
    return credentialMappingsClient.remove(tenantId, mappingId);
  }

  // ============ Contracts / UAC (CAB-1649) ============

  async getContracts(tenantId: string): Promise<ContractListResponse> {
    return contractsClient.list(tenantId);
  }

  async getContract(tenantId: string, contractId: string): Promise<Contract> {
    return contractsClient.get(tenantId, contractId);
  }

  async createContract(tenantId: string, payload: ContractCreate): Promise<Contract> {
    return contractsClient.create(tenantId, payload);
  }

  async publishContract(tenantId: string, contractId: string): Promise<PublishContractResponse> {
    return contractsClient.publish(tenantId, contractId);
  }

  async updateContract(
    tenantId: string,
    contractId: string,
    payload: Schemas['ContractUpdate']
  ): Promise<Contract> {
    return contractsClient.update(tenantId, contractId, payload);
  }

  async deleteContract(tenantId: string, contractId: string): Promise<void> {
    return contractsClient.remove(tenantId, contractId);
  }

  async getContractBindings(tenantId: string, contractId: string): Promise<ProtocolBinding[]> {
    return contractsClient.listBindings(tenantId, contractId);
  }

  async enableBinding(
    tenantId: string,
    contractId: string,
    protocol: string
  ): Promise<ProtocolBinding> {
    return contractsClient.enableBinding(tenantId, contractId, protocol);
  }

  async disableBinding(tenantId: string, contractId: string, protocol: string): Promise<void> {
    return contractsClient.disableBinding(tenantId, contractId, protocol);
  }

  // ============ Monitoring / Call Flow (CAB-1869) ============

  async getTransactions(
    limit = 20,
    status?: string,
    timeRange?: string,
    serviceType?: string,
    statusCode?: number,
    route?: string
  ): Promise<{ transactions: MonitoringTransaction[] }> {
    const params: Record<string, string | number> = { limit };
    if (status) params.status = status;
    if (timeRange) params.time_range = timeRange;
    if (serviceType) params.service_type = serviceType;
    if (statusCode) params.status_code = statusCode;
    if (route) params.route = route;
    const { data } = await httpClient.get('/v1/monitoring/transactions', { params });
    return data;
  }

  async getTransactionDetail(transactionId: string): Promise<MonitoringTransactionDetail> {
    const { data } = await httpClient.get(`/v1/monitoring/transactions/${transactionId}`);
    return data;
  }

  async getTransactionStats(timeRange?: string): Promise<MonitoringStats> {
    const params: Record<string, string> = {};
    if (timeRange) params.time_range = timeRange;
    const { data } = await httpClient.get('/v1/monitoring/transactions/stats', { params });
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
  deployment_mode?: string;
  spans?: Array<{
    name: string;
    service: string;
    start_offset_ms: number;
    duration_ms: number;
    status: string;
  }>;
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
  requests_per_minute: number;
  by_api: Record<string, number>;
  by_status_code: Record<string, number>;
}

export const apiService = new ApiService();
