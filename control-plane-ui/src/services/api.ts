import type {
  Tenant,
  TenantCreate,
  API,
  APIOpenAPISpec,
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
  AggregatedMetrics,
  DeploymentStatusSummary,
  GatewayDeployment,
  GatewayGuardrailsResponse,
  GatewayHealthSummary,
  GatewayInstance,
  GatewayInstanceCreate,
  GatewayInstanceMetrics,
  GatewayInstanceUpdate,
  GatewayModeStats,
  GatewayPolicy,
  PaginatedGatewayDeployments,
  PaginatedGatewayInstances,
} from '../types';
import type { Schemas } from '@stoa/shared/api-types';
import {
  httpClient,
  setAuthToken as setAuthTokenCore,
  getAuthToken as getAuthTokenCore,
  clearAuthToken as clearAuthTokenCore,
  setTokenRefresher as setTokenRefresherCore,
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
import { deploymentsClient } from './api/deployments';
import { tracesClient } from './api/traces';
import { gatewaysClient } from './api/gateways';
import { gatewayDeploymentsClient } from './api/gatewayDeployments';
import { platformClient } from './api/platform';
import { chatClient } from './api/chat';
import { llmClient } from './api/llm';
import { monitoringClient } from './api/monitoring';
import { apiLifecycleClient } from './api/apiLifecycle';

// Imports internes des types co-localisés (nécessaires pour les signatures de
// la classe ApiService ci-dessous). Ré-exports publics : voir en bas de fichier.
import type {
  OperationsMetrics,
  BusinessMetrics,
  TopAPI,
  ComponentStatus,
  PlatformEvent,
  PlatformStatusResponse,
  ApplicationDiffResponse,
} from './api/platform';
import type {
  TenantChatSettings,
  ChatUsageBySource,
  TokenBudgetStatus,
  TokenUsageStats,
  ChatConversationMetrics,
  ChatModelDistribution,
} from './api/chat';
import type {
  LlmUsageResponse,
  LlmTimeseriesResponse,
  LlmProviderBreakdownResponse,
  LlmBudgetResponse,
} from './api/llm';
import type {
  MonitoringTransaction,
  MonitoringTransactionDetail,
  MonitoringStats,
} from './api/monitoring';
import type {
  ApiLifecycleCreateDraftRequest,
  ApiLifecycleState,
  ApiLifecycleValidateDraftRequest,
  ApiLifecycleValidateDraftResponse,
  ApiLifecycleDeploymentRequest,
  ApiLifecycleDeployResponse,
  ApiLifecyclePublicationRequest,
  ApiLifecyclePublishResponse,
  ApiLifecyclePromotionRequest,
  ApiLifecyclePromotionResponse,
} from './api/apiLifecycle';

// ── Type re-exports (historiquement inline en bas de api.ts) ─────────────────
// Ces types sont désormais co-localisés avec leur client de domaine.
// On ré-exporte par sous-chemin explicite (pas de api/index.ts — collision
// de résolution avec le fichier api.ts, cf. REWRITE-PLAN § C).
export type {
  OperationsMetrics,
  BusinessMetrics,
  TopAPI,
  ComponentStatus,
  GitOpsStatus,
  PlatformEvent,
  ExternalLinks,
  PlatformStatusResponse,
  ApplicationDiffResource,
  ApplicationDiffResponse,
} from './api/platform';
export type {
  TenantChatSettings,
  ChatSourceEntry,
  ChatUsageBySource,
  TokenBudgetStatus,
  TokenUsageStats,
  ChatConversationMetrics,
  ModelDistributionEntry,
  ChatModelDistribution,
} from './api/chat';
export type {
  LlmUsageResponse,
  LlmTimeseriesPoint,
  LlmTimeseriesResponse,
  LlmProviderCostEntry,
  LlmProviderBreakdownResponse,
  LlmBudgetResponse,
} from './api/llm';
export type {
  MonitoringTransaction,
  MonitoringTransactionDetail,
  MonitoringStats,
} from './api/monitoring';
export type {
  ApiLifecycleCreateDraftRequest,
  ApiLifecycleGatewayDeployment,
  ApiLifecycleState,
  ApiLifecycleValidateDraftRequest,
  ApiLifecycleValidateDraftResponse,
  ApiLifecycleDeploymentRequest,
  ApiLifecycleDeployResponse,
  ApiLifecyclePublicationRequest,
  ApiLifecyclePublishResponse,
  ApiLifecyclePromotionRequest,
  ApiLifecyclePromotionResponse,
} from './api/apiLifecycle';

// =============================================================================
// Façade ApiService — agrège le core transport (services/http) et tous les
// clients de domaine (services/api/*.ts). Aucune logique métier ici : chaque
// méthode délègue soit à `httpClient` (passthrough générique), soit à un
// client de domaine.
//
// Contrat publié : le type `LegacyApiSurface` (alias de `ApiService`) est la
// forme consommée par les ~76 callers et les 56 `vi.mock('../services/api')`
// du projet. TypeScript vérifie à la compilation que chaque méthode listée
// ici a bien une implémentation : toute dérive casse `tsc --noEmit` avec un
// message précis, pas un smoke test de cardinalité.
//
// Les nouveaux callers peuvent importer directement `{ tenantsClient }`
// depuis `@/services/api/tenants` — la façade subsiste tant que UI-3 n'a pas
// migré tous les usages + mocks de tests.
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
  }

  getAuthToken(): string | null {
    return getAuthTokenCore();
  }

  clearAuthToken(): void {
    clearAuthTokenCore();
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

  async getApiOpenApiSpec(tenantId: string, apiId: string): Promise<APIOpenAPISpec> {
    return apisClient.getOpenApiSpec(tenantId, apiId);
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

  // Canonical API lifecycle
  async createLifecycleDraft(
    tenantId: string,
    request: ApiLifecycleCreateDraftRequest
  ): Promise<ApiLifecycleState> {
    return apiLifecycleClient.createDraft(tenantId, request);
  }

  async getApiLifecycleState(tenantId: string, apiId: string): Promise<ApiLifecycleState> {
    return apiLifecycleClient.getState(tenantId, apiId);
  }

  async validateLifecycleDraft(
    tenantId: string,
    apiId: string,
    request: ApiLifecycleValidateDraftRequest = {}
  ): Promise<ApiLifecycleValidateDraftResponse> {
    return apiLifecycleClient.validateDraft(tenantId, apiId, request);
  }

  async deployLifecycleApi(
    tenantId: string,
    apiId: string,
    request: ApiLifecycleDeploymentRequest
  ): Promise<ApiLifecycleDeployResponse> {
    return apiLifecycleClient.deploy(tenantId, apiId, request);
  }

  async publishLifecycleApi(
    tenantId: string,
    apiId: string,
    request: ApiLifecyclePublicationRequest
  ): Promise<ApiLifecyclePublishResponse> {
    return apiLifecycleClient.publish(tenantId, apiId, request);
  }

  async promoteLifecycleApi(
    tenantId: string,
    apiId: string,
    request: ApiLifecyclePromotionRequest
  ): Promise<ApiLifecyclePromotionResponse> {
    return apiLifecycleClient.promote(tenantId, apiId, request);
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
    return deploymentsClient.list(tenantId, params);
  }

  async getDeployment(tenantId: string, deploymentId: string): Promise<Deployment> {
    return deploymentsClient.get(tenantId, deploymentId);
  }

  async createDeployment(tenantId: string, request: DeploymentCreate): Promise<Deployment> {
    return deploymentsClient.create(tenantId, request);
  }

  async rollbackDeployment(
    tenantId: string,
    deploymentId: string,
    targetVersion?: string
  ): Promise<Deployment> {
    return deploymentsClient.rollback(tenantId, deploymentId, targetVersion);
  }

  async getDeploymentLogs(
    tenantId: string,
    deploymentId: string,
    afterSeq: number = 0,
    limit: number = 200
  ): Promise<DeploymentLogListResponse> {
    return deploymentsClient.getLogs(tenantId, deploymentId, afterSeq, limit);
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
    return deploymentsClient.getEnvironmentStatus(tenantId, environment);
  }

  // Git
  async getCommits(tenantId: string, path?: string): Promise<CommitInfo[]> {
    return gitClient.listCommits(tenantId, path);
  }

  async getMergeRequests(tenantId: string): Promise<MergeRequest[]> {
    return gitClient.listMergeRequests(tenantId);
  }

  // SSE Events — callers migrated to openEventStream from services/http (C4).

  // Pipeline Traces
  async getTraces(
    limit?: number,
    tenantId?: string,
    status?: string,
    environment?: string
  ): Promise<{ traces: TraceSummary[]; total: number }> {
    return tracesClient.list(limit, tenantId, status, environment);
  }

  async getTrace(traceId: string): Promise<PipelineTrace> {
    return tracesClient.get(traceId);
  }

  async getTraceTimeline(traceId: string): Promise<TraceTimeline> {
    return tracesClient.getTimeline(traceId);
  }

  async getTraceStats(): Promise<TraceStats> {
    return tracesClient.getStats();
  }

  async getLiveTraces(): Promise<{ traces: PipelineTrace[]; count: number }> {
    return tracesClient.listLive();
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getAiSessionStats(days?: number, worker?: string): Promise<any> {
    return tracesClient.getAiSessionStats(days, worker);
  }

  async exportAiSessionsCsv(days?: number, worker?: string): Promise<Blob> {
    return tracesClient.exportAiSessionsCsv(days, worker);
  }

  // Platform Status (CAB-654)
  async getPlatformStatus(): Promise<PlatformStatusResponse> {
    return platformClient.getStatus();
  }

  async getPlatformComponents(): Promise<ComponentStatus[]> {
    return platformClient.listComponents();
  }

  async getComponentStatus(name: string): Promise<ComponentStatus> {
    return platformClient.getComponent(name);
  }

  async syncPlatformComponent(name: string): Promise<{ message: string; operation: string }> {
    return platformClient.syncComponent(name);
  }

  async getComponentDiff(name: string): Promise<ApplicationDiffResponse> {
    return platformClient.getComponentDiff(name);
  }

  async getPlatformEvents(component?: string, limit?: number): Promise<PlatformEvent[]> {
    return platformClient.listEvents(component, limit);
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
  }): Promise<PaginatedGatewayInstances> {
    return gatewaysClient.listInstances(params);
  }

  async getGatewayInstance(id: string): Promise<GatewayInstance> {
    return gatewaysClient.getInstance(id);
  }

  async getGatewayTools(id: string): Promise<Schemas['ListToolsResponse']['tools']> {
    return gatewaysClient.listTools(id);
  }

  async createGatewayInstance(payload: GatewayInstanceCreate): Promise<GatewayInstance> {
    return gatewaysClient.createInstance(payload);
  }

  async updateGatewayInstance(
    id: string,
    payload: GatewayInstanceUpdate
  ): Promise<GatewayInstance> {
    return gatewaysClient.updateInstance(id, payload);
  }

  async deleteGatewayInstance(id: string): Promise<void> {
    return gatewaysClient.removeInstance(id);
  }

  async restoreGatewayInstance(id: string): Promise<GatewayInstance> {
    return gatewaysClient.restoreInstance(id);
  }

  async checkGatewayHealth(id: string): Promise<Schemas['GatewayHealthCheckResponse']> {
    return gatewaysClient.checkHealth(id);
  }

  async getGatewayModeStats(): Promise<GatewayModeStats> {
    return gatewaysClient.getModeStats();
  }

  // Gateway Deployments
  async getDeploymentStatusSummary(): Promise<DeploymentStatusSummary> {
    return gatewayDeploymentsClient.getStatusSummary();
  }

  async getGatewayDeployments(params?: {
    sync_status?: string;
    gateway_instance_id?: string;
    environment?: string;
    gateway_type?: string;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedGatewayDeployments> {
    return gatewayDeploymentsClient.list(params);
  }

  async getGatewayDeployment(id: string): Promise<GatewayDeployment> {
    return gatewayDeploymentsClient.get(id);
  }

  async deployApiToGateways(payload: {
    api_catalog_id: string;
    gateway_instance_ids: string[];
  }): Promise<GatewayDeployment[]> {
    return gatewayDeploymentsClient.deployApiToGateways(payload);
  }

  async undeployFromGateway(id: string): Promise<void> {
    return gatewayDeploymentsClient.undeploy(id);
  }

  async forceSyncDeployment(id: string): Promise<GatewayDeployment> {
    return gatewayDeploymentsClient.forceSync(id);
  }

  async testDeployment(id: string): Promise<{
    reachable: boolean;
    status_code?: number;
    latency_ms?: number;
    error?: string;
    gateway_url?: string;
    path?: string;
  }> {
    return gatewayDeploymentsClient.test(id);
  }

  async getCatalogEntries(): Promise<
    { id: string; api_name: string; tenant_id: string; version: string }[]
  > {
    return gatewayDeploymentsClient.listCatalogEntries();
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
    return deploymentsClient.getDeployableEnvironments(tenantId, apiId);
  }

  async deployApiToEnv(
    tenantId: string,
    apiId: string,
    payload: { environment: string; gateway_ids?: string[] }
  ): Promise<{ deployed: number; environment: string; deployment_ids: string[] }> {
    return deploymentsClient.deployApiToEnv(tenantId, apiId, payload);
  }

  async getApiGatewayAssignments(
    tenantId: string,
    apiId: string,
    environment?: string
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ): Promise<{ items: any[]; total: number }> {
    return deploymentsClient.getApiGatewayAssignments(tenantId, apiId, environment);
  }

  async createApiGatewayAssignment(
    tenantId: string,
    apiId: string,
    payload: { gateway_id: string; environment: string; auto_deploy: boolean }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ): Promise<any> {
    return deploymentsClient.createApiGatewayAssignment(tenantId, apiId, payload);
  }

  async deleteApiGatewayAssignment(
    tenantId: string,
    apiId: string,
    assignmentId: string
  ): Promise<void> {
    return deploymentsClient.deleteApiGatewayAssignment(tenantId, apiId, assignmentId);
  }

  // =========================================================================
  // Gateway Observability
  // =========================================================================

  async getGatewayAggregatedMetrics(): Promise<AggregatedMetrics> {
    return gatewaysClient.getAggregatedMetrics();
  }

  async getGuardrailsEvents(limit = 20): Promise<GatewayGuardrailsResponse> {
    return gatewaysClient.getGuardrailsEvents(limit);
  }

  async getGatewayHealthSummary(): Promise<GatewayHealthSummary> {
    return gatewaysClient.getHealthSummary();
  }

  async getGatewayInstanceMetrics(id: string): Promise<GatewayInstanceMetrics> {
    return gatewaysClient.getInstanceMetrics(id);
  }

  // =========================================================================
  // Gateway Policies
  // =========================================================================

  async getGatewayPolicies(params?: {
    tenant_id?: string;
    environment?: string;
  }): Promise<GatewayPolicy[]> {
    return gatewaysClient.listPolicies(params);
  }

  async createGatewayPolicy(payload: Schemas['GatewayPolicyCreate']): Promise<GatewayPolicy> {
    return gatewaysClient.createPolicy(payload);
  }

  async updateGatewayPolicy(
    id: string,
    payload: Schemas['GatewayPolicyUpdate']
  ): Promise<GatewayPolicy> {
    return gatewaysClient.updatePolicy(id, payload);
  }

  async deleteGatewayPolicy(id: string): Promise<void> {
    return gatewaysClient.removePolicy(id);
  }

  async createPolicyBinding(
    payload: Schemas['PolicyBindingCreate']
  ): Promise<Schemas['PolicyBindingResponse']> {
    return gatewaysClient.createPolicyBinding(payload);
  }

  async deletePolicyBinding(id: string): Promise<void> {
    return gatewaysClient.removePolicyBinding(id);
  }

  // =========================================================================
  // Operations Dashboard (CAB-Observability)
  // =========================================================================

  async getOperationsMetrics(): Promise<OperationsMetrics> {
    return platformClient.getOperationsMetrics();
  }

  // =========================================================================
  // Business Analytics (CAB-Observability)
  // =========================================================================

  async getBusinessMetrics(): Promise<BusinessMetrics> {
    return platformClient.getBusinessMetrics();
  }

  async getTopAPIs(limit = 10): Promise<TopAPI[]> {
    return platformClient.getTopAPIs(limit);
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
    return chatClient.getSettings(tenantId);
  }

  async updateChatSettings(
    tenantId: string,
    settings: Partial<TenantChatSettings>
  ): Promise<TenantChatSettings> {
    return chatClient.updateSettings(tenantId, settings);
  }

  // Chat Token Metering (CAB-288)
  async getChatBudgetStatus(tenantId: string): Promise<TokenBudgetStatus> {
    return chatClient.getBudgetStatus(tenantId);
  }

  async getChatUsageStats(tenantId: string, days = 30): Promise<TokenUsageStats> {
    return chatClient.getUsageStats(tenantId, days);
  }

  // Chat Usage by source — per-app breakdown (CAB-1868)
  async getChatUsageTenant(
    tenantId: string,
    params: { group_by?: string; days?: number } = {}
  ): Promise<ChatUsageBySource> {
    return chatClient.getUsageBySource(tenantId, params);
  }

  // Chat conversation metrics — tenant-level aggregates (CAB-1868)
  async getChatConversationMetrics(tenantId: string): Promise<ChatConversationMetrics> {
    return chatClient.getConversationMetrics(tenantId);
  }

  // Chat model distribution — conversations per model (CAB-1868)
  async getChatModelDistribution(tenantId: string): Promise<ChatModelDistribution> {
    return chatClient.getModelDistribution(tenantId);
  }

  async createChatConversation(
    tenantId: string,
    title = 'New conversation'
  ): Promise<{ id: string }> {
    return chatClient.createConversation(tenantId, title);
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
    return llmClient.getUsage(tenantId, period);
  }

  async getLlmTimeseries(
    tenantId: string,
    period: 'hour' | 'day' | 'week' | 'month' = 'week'
  ): Promise<LlmTimeseriesResponse> {
    return llmClient.getTimeseries(tenantId, period);
  }

  async getLlmProviderBreakdown(
    tenantId: string,
    period: 'hour' | 'day' | 'week' | 'month' = 'month'
  ): Promise<LlmProviderBreakdownResponse> {
    return llmClient.getProviderBreakdown(tenantId, period);
  }

  async getLlmBudget(tenantId: string): Promise<LlmBudgetResponse> {
    return llmClient.getBudget(tenantId);
  }

  async updateLlmBudget(
    tenantId: string,
    update: { monthly_limit_usd?: number; alert_threshold_pct?: number }
  ): Promise<LlmBudgetResponse> {
    return llmClient.updateBudget(tenantId, update);
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

  async revokeSubscription(id: string, reason: string): Promise<Subscription> {
    return subscriptionsClient.revoke(id, reason);
  }

  async suspendSubscription(id: string): Promise<Subscription> {
    return subscriptionsClient.suspend(id);
  }

  async reactivateSubscription(id: string): Promise<Subscription> {
    return subscriptionsClient.reactivate(id);
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
    return monitoringClient.listTransactions(
      limit,
      status,
      timeRange,
      serviceType,
      statusCode,
      route
    );
  }

  async getTransactionDetail(transactionId: string): Promise<MonitoringTransactionDetail> {
    return monitoringClient.getTransactionDetail(transactionId);
  }

  async getTransactionStats(timeRange?: string): Promise<MonitoringStats> {
    return monitoringClient.getTransactionStats(timeRange);
  }
}

/**
 * Public shape of the legacy façade. Exported so tests and future consumers
 * can type their mocks without duplicating signatures.
 *
 * Amendement UI-2 (2026-04-22) : cet alias remplace le smoke test
 * `Object.keys(apiService).length === ATTENDU` par un contrat nominal
 * vérifié par `tsc`.
 */
export type LegacyApiSurface = ApiService;

export const apiService: LegacyApiSurface = new ApiService();
