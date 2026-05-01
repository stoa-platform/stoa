// =============================================================================
// View-models, narrowed enums, and UI-only types.
//
// Wire formats live in `@stoa/shared/api-types` (`Schemas['XxxResponse']`)
// and are imported here to build view-models when needed (drift, enrichment).
// =============================================================================

import type { Schemas } from '@stoa/shared/api-types';

// ---- User / Auth ------------------------------------------------------------
//
// `User` is a session-local view-model assembled from the OIDC token + the
// `/me` endpoint. It is NOT the wire type — see `Schemas['UserPermissionsResponse']`
// for the raw `/me` payload.
export interface User {
  id: string;
  email: string;
  name: string;
  username: string;
  roles: string[];
  tenant_id?: string;
  permissions: string[];
  role_display_names?: Record<string, string>;
}

export type Role = 'cpi-admin' | 'tenant-admin' | 'devops' | 'viewer';

// `Permission` mirrors what UI consumers expect; backend nests this under
// `RoleResponse.permissions` without extracting a named schema (BUG-5).
export interface Permission {
  name: string;
  description: string;
}

// ---- Tenant -----------------------------------------------------------------
// Wire alias. Status is `string` at the wire level — UI status maps must be
// typed `Record<string, ...>`. Nullable timestamps require guards.
export type Tenant = Schemas['TenantResponse'];

// Intentionally narrower than `Schemas['TenantCreate']` (which requires
// `description` and `owner_email`). UI flows currently only send these two.
export interface TenantCreate {
  name: string;
  display_name: string;
}

// ---- API (catalog entity) ---------------------------------------------------
// Wire = `Schemas['APIResponse']`. Post-CAB-2159 the backend declares
// `audience`, `created_at`, `updated_at` directly — only `openapi_spec` stays
// UI-side (fetched from a separate endpoint, not embedded in APIResponse).
export type API = Schemas['APIResponse'] & {
  openapi_spec?: string | Record<string, unknown>;
  catalog_release_id?: string | null;
  catalog_release_tag?: string | null;
  catalog_pr_url?: string | null;
  catalog_pr_number?: number | null;
  catalog_source_branch?: string | null;
  catalog_merge_commit_sha?: string | null;
};

export interface APICreate {
  name: string;
  display_name: string;
  version: string;
  description: string;
  backend_url: string;
  openapi_spec?: string;
  tags?: string[];
  portal_promoted?: boolean; // Add portal:published tag when true
}

// ---- Application ------------------------------------------------------------
// Wire = `Schemas['ApplicationResponse']` (BUG-1 resolved in backend via
// CAB-2159). `client_id` and `tenant_id` stay nullable at the wire layer —
// consumers must guard before string operations. Regression CAB-2159 covers
// alias parity with the canonical schema.
export type Application = Schemas['ApplicationResponse'] & {
  /** UI-only field, populated client-side via filters/context. */
  environment?: string;
};

export type SecurityProfile =
  | 'api_key'
  | 'oauth2_public'
  | 'oauth2_confidential'
  | 'fapi_baseline'
  | 'fapi_advanced';

export interface ApplicationCreate {
  name: string;
  display_name: string;
  description: string;
  redirect_uris: string[];
  api_subscriptions: string[];
  security_profile?: SecurityProfile;
  jwks_uri?: string;
  jwks?: string; // Inline PEM or JWK/JWKS JSON
}

// Consumer types (CAB-864 — mTLS Self-Service)
export type CertificateStatus = 'active' | 'rotating' | 'revoked' | 'expired';

// Backend emits `certificate_status: string | null`. Coerce unknown/null to
// `undefined` so `CertificateHealthBadge` (undefined-tolerant) never receives
// a silent `null`.
export function normalizeCertificateStatus(
  value: string | null | undefined
): CertificateStatus | undefined {
  if (value === 'active' || value === 'rotating' || value === 'revoked' || value === 'expired') {
    return value;
  }
  return undefined;
}

// Token binding mode (CAB-438 — Sender-Constrained Tokens)
export type TokenBindingMode = 'mtls' | 'dpop' | 'none';

// Wire = `Schemas['ConsumerResponse']`. UI ENRICHES with `dpop_jkt` (RFC 9449
// DPoP thumbprint, CAB-438). `certificate_status` is widened to
// `CertificateStatus` union via `as` casts at consumer sites.
export type Consumer = Schemas['ConsumerResponse'] & {
  /** DPoP JWK Thumbprint (RFC 9449) — set when DPoP binding is active. */
  dpop_jkt?: string;
};

// Certificate lifecycle types (CAB-872)
// Tenant CA types (CAB-1787/1788 — per-tenant CA management)
export interface TenantCAInfo {
  tenant_id: string;
  subject_dn: string;
  serial_number: string;
  not_before: string;
  not_after: string;
  key_algorithm: string;
  fingerprint_sha256: string;
  ca_certificate_pem: string;
  status: string;
  created_at?: string;
}

export interface IssuedCertificate {
  id: string;
  subject_dn: string;
  issuer_dn: string;
  serial_number: string;
  fingerprint_sha256: string;
  not_before: string;
  not_after: string;
  key_algorithm: string;
  status: string;
  consumer_id: string | null;
  created_by: string | null;
  created_at: string;
  revoked_at: string | null;
}

export interface IssuedCertificateListResponse {
  items: IssuedCertificate[];
  total: number;
}

// Environment types (ADR-040 — Born GitOps)
export type Environment = 'dev' | 'staging' | 'prod';
export type EnvironmentMode = 'full' | 'read-only' | 'promote-only';

export interface EnvironmentEndpoints {
  api_url: string;
  keycloak_url: string;
  keycloak_realm: string;
  mcp_url: string;
}

export interface EnvironmentConfig {
  name: string;
  label: string;
  mode: EnvironmentMode;
  color: string;
  endpoints?: EnvironmentEndpoints | null;
  is_current?: boolean;
}

// Deployment types (CAB-1353 lifecycle API)
export type DeploymentStatus = 'pending' | 'in_progress' | 'success' | 'failed' | 'rolled_back';

export interface Deployment {
  id: string;
  tenant_id: string;
  api_id: string;
  api_name: string;
  environment: string;
  version: string;
  status: DeploymentStatus;
  deployed_by: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  error_message?: string;
  rollback_of?: string;
  rollback_version?: string;
  gateway_id?: string;
  spec_hash?: string;
  commit_sha?: string;
  attempt_count: number;
}

export interface DeploymentCreate {
  api_id: string;
  environment: string;
  api_name?: string;
  version?: string;
  gateway_id?: string;
}

export interface DeploymentListResponse {
  items: Deployment[];
  total: number;
  page: number;
  page_size: number;
}

export type DeployLogLevel = 'info' | 'warn' | 'error' | 'debug';

export interface DeploymentLog {
  id: string;
  deployment_id: string;
  tenant_id: string;
  seq: number;
  level: DeployLogLevel;
  step?: string;
  message: string;
  created_at: string;
}

export interface DeploymentLogListResponse {
  items: DeploymentLog[];
  total: number;
}

export interface EnvironmentStatusDeployment {
  api_id: string;
  api_name: string;
  version: string;
  status: string;
  deployed_at?: string;
}

export interface EnvironmentStatusResponse {
  environment: string;
  healthy: boolean;
  deployments: EnvironmentStatusDeployment[];
}

// Event types
export interface Event {
  id: string;
  type: string;
  tenant_id: string;
  timestamp: string;
  user_id?: string;
  payload: Record<string, unknown>;
}

// Git types
export interface CommitInfo {
  sha: string;
  message: string;
  author: string;
  date: string;
}

export interface MergeRequest {
  id: number;
  iid: number;
  title: string;
  description: string;
  state: 'opened' | 'merged' | 'closed';
  source_branch: string;
  target_branch: string;
  web_url: string;
  created_at: string;
  author: string;
}

// Pipeline Trace types
export type TraceStatus = 'pending' | 'in_progress' | 'success' | 'failed' | 'skipped';

export interface TraceStep {
  name: string;
  status: TraceStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  details?: Record<string, unknown>;
  error?: string;
}

export interface TraceSummary {
  id: string;
  trigger_type: string;
  trigger_source: string;
  tenant_id?: string;
  api_name?: string;
  git_author?: string;
  git_commit_sha?: string;
  git_commit_message?: string;
  status: TraceStatus;
  created_at: string;
  total_duration_ms?: number;
  steps_count: number;
  steps_completed: number;
  steps_failed: number;
  cost_usd?: number;
  total_tokens?: number;
  model?: string;
}

export interface PipelineTrace {
  id: string;
  trigger_type: string;
  trigger_source: string;
  git_commit_sha?: string;
  git_commit_message?: string;
  git_branch?: string;
  git_author?: string;
  git_author_email?: string;
  git_project?: string;
  git_files_changed?: string[];
  tenant_id?: string;
  api_id?: string;
  api_name?: string;
  environment?: string;
  created_at: string;
  completed_at?: string;
  total_duration_ms?: number;
  status: TraceStatus;
  steps: TraceStep[];
  error_summary?: string;
}

export interface TraceTimeline {
  trace_id: string;
  trigger: {
    type: string;
    source: string;
    author?: string;
    commit?: string;
    message?: string;
  };
  target: {
    tenant_id?: string;
    api_name?: string;
    environment?: string;
  };
  status: TraceStatus;
  created_at: string;
  total_duration_ms?: number;
  timeline: TraceStep[];
  error_summary?: string;
}

export interface TraceStats {
  total: number;
  by_status: Record<string, number>;
  avg_duration_ms: number;
  success_rate: number;
}

// MCP Tool types
export interface ToolInputSchema {
  type: 'object';
  properties: Record<string, ToolPropertySchema>;
  required?: string[];
}

export interface ToolPropertySchema {
  type: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  items?: ToolPropertySchema;
  properties?: Record<string, ToolPropertySchema>;
}

export interface MCPTool {
  name: string;
  description: string;
  inputSchema: ToolInputSchema;
  apiId?: string;
  tenantId?: string;
  endpoint?: string;
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  tags?: string[];
  version?: string;
  annotations?: Record<string, unknown>;
}

export interface ListToolsResponse {
  tools: MCPTool[];
  nextCursor?: string;
  totalCount: number;
}

export interface ToolUsageStats {
  toolName: string;
  totalCalls: number;
  successCount: number;
  errorCount: number;
  avgLatencyMs: number;
  totalCostUnits: number;
  lastInvokedAt?: string;
}

export interface ToolUsageSummary {
  period: string;
  startDate: string;
  endDate: string;
  totalCalls: number;
  successRate: number;
  totalCostUnits: number;
  avgLatencyMs: number;
  toolBreakdown: ToolUsageStats[];
}

export interface ToolSubscription {
  id: string;
  userId: string;
  toolName: string;
  subscribedAt: string;
  status: 'active' | 'suspended' | 'pending';
  usageLimit?: number;
  usageCount: number;
}

export interface ToolSubscriptionCreate {
  toolName: string;
  usageLimit?: number;
}

// Error Snapshot types — gateway-agnostic (matches CP API /v1/snapshots)
export type SnapshotTrigger = '4xx' | '5xx' | 'timeout' | 'manual';
export type SnapshotResolutionStatus = 'unresolved' | 'investigating' | 'resolved' | 'ignored';

export interface ErrorSnapshotSummary {
  id: string;
  timestamp: string;
  tenant_id: string;
  trigger: SnapshotTrigger;
  status: number;
  method: string;
  path: string;
  duration_ms: number;
  source: string;
  resolution_status: SnapshotResolutionStatus;
}

export interface SnapshotRequest {
  method: string;
  path: string;
  headers: Record<string, string>;
  body?: unknown;
  query_params: Record<string, string>;
  client_ip?: string;
  user_agent?: string;
}

export interface SnapshotResponse {
  status: number;
  headers: Record<string, string>;
  body?: unknown;
  duration_ms: number;
}

export interface SnapshotRouting {
  api_name?: string;
  api_version?: string;
  route?: string;
  backend_url?: string;
}

export interface SnapshotBackendState {
  health: string;
  last_success?: string;
  error_rate_1m?: number;
  p99_latency_ms?: number;
}

export interface SnapshotEnvironment {
  pod?: string;
  node?: string;
  namespace?: string;
  memory_percent?: number;
  cpu_percent?: number;
}

export interface ErrorSnapshotDetail {
  id: string;
  timestamp: string;
  tenant_id: string;
  trigger: SnapshotTrigger;
  request: SnapshotRequest;
  response: SnapshotResponse;
  routing: SnapshotRouting;
  backend_state: SnapshotBackendState;
  trace_id?: string;
  span_id?: string;
  environment: SnapshotEnvironment;
  masked_fields: string[];
  source: string;
  resolution_status: SnapshotResolutionStatus;
  resolution_notes?: string;
}

export interface ErrorSnapshotStats {
  total: number;
  by_trigger: Record<string, number>;
  by_status_code: Record<number, number>;
  resolution_stats: {
    unresolved: number;
    investigating: number;
    resolved: number;
    ignored: number;
  };
  period: { start?: string; end?: string };
}

export interface ErrorSnapshotFilters {
  trigger?: SnapshotTrigger;
  status_code?: number;
  source?: string;
  resolution_status?: SnapshotResolutionStatus;
  start_date?: string;
  end_date?: string;
  path_contains?: string;
}

export interface ErrorSnapshotListResponse {
  items: ErrorSnapshotSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface SnapshotFiltersResponse {
  triggers: string[];
  sources: string[];
  status_codes: number[];
  resolution_statuses: string[];
}

// =============================================================================
// API Transaction Monitoring types (E2E Tracing)
// =============================================================================

export type TransactionStatus = 'success' | 'error' | 'timeout' | 'pending';

export interface TransactionSpan {
  name: string;
  service: string;
  status: TransactionStatus;
  start_offset_ms: number;
  duration_ms: number;
  started_at?: string;
  error?: string;
  metadata?: Record<string, unknown>;
}

export interface APITransaction {
  id: string;
  trace_id: string;
  api_name: string;
  tenant_id: string;
  method: string;
  path: string;
  status_code: number;
  status: TransactionStatus;
  status_text?: string;
  error_source?: string;
  client_ip?: string;
  user_id?: string;
  started_at: string;
  total_duration_ms: number;
  spans: TransactionSpan[];
  request_headers?: Record<string, string>;
  response_headers?: Record<string, string>;
  error_message?: string;
  demo_mode?: boolean;
}

export interface APITransactionSummary {
  id: string;
  trace_id: string;
  api_name: string;
  method: string;
  path: string;
  status_code: number;
  status: TransactionStatus;
  status_text?: string;
  error_source?: string;
  started_at: string;
  total_duration_ms: number;
  spans_count: number;
}

export interface APITransactionStats {
  total_requests: number;
  success_count: number;
  error_count: number;
  timeout_count: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  requests_per_minute: number;
  by_api: Record<
    string,
    {
      total: number;
      success: number;
      errors: number;
      avg_latency_ms: number;
    }
  >;
  by_status_code: Record<number, number>;
}

// =============================================================================
// Platform Status types (CAB-654 - GitOps Observability)
// =============================================================================

export type ComponentHealth = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
export type GitOpsSyncStatus = 'Synced' | 'OutOfSync' | 'Unknown' | 'NotFound' | 'Error';
export type GitOpsHealthStatus =
  | 'Healthy'
  | 'Degraded'
  | 'Progressing'
  | 'Suspended'
  | 'Missing'
  | 'Unknown';
export type PlatformEventSeverity = 'info' | 'warning' | 'error';

export interface ComponentStatus {
  name: string;
  display_name: string;
  sync_status: GitOpsSyncStatus;
  health_status: GitOpsHealthStatus;
  revision: string;
  last_sync: string | null;
  message: string | null;
}

export interface GitOpsStatus {
  status: 'healthy' | 'degraded' | 'syncing' | 'unknown';
  components: ComponentStatus[];
  checked_at: string;
}

export interface PlatformEvent {
  id?: number;
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

// =============================================================================
// External MCP Server Types
// =============================================================================

export type ExternalMCPTransport = 'sse' | 'http' | 'websocket';
export type ExternalMCPAuthType = 'none' | 'api_key' | 'bearer_token' | 'oauth2';
export type ExternalMCPHealthStatus = 'unknown' | 'healthy' | 'degraded' | 'unhealthy';

export interface ExternalMCPServerTool {
  id: string;
  name: string;
  namespaced_name: string;
  display_name?: string;
  description?: string;
  input_schema?: Record<string, unknown>;
  enabled: boolean;
  synced_at: string;
}

export interface ExternalMCPServer {
  id: string;
  name: string;
  display_name: string;
  description?: string;
  icon?: string;
  base_url: string;
  transport: ExternalMCPTransport;
  auth_type: ExternalMCPAuthType;
  tool_prefix?: string;
  enabled: boolean;
  is_platform?: boolean;
  health_status: ExternalMCPHealthStatus;
  last_health_check?: string;
  last_sync_at?: string;
  sync_error?: string;
  tenant_id?: string;
  environment?: string;
  gateway_instance_id?: string;
  tools_count: number;
  created_at: string;
  updated_at: string;
  created_by?: string;
}

export interface ExternalMCPServerDetail extends ExternalMCPServer {
  tools: ExternalMCPServerTool[];
}

export interface OAuth2Credentials {
  client_id: string;
  client_secret: string;
  token_url: string;
  scope?: string;
}

export interface ExternalMCPServerCredentials {
  api_key?: string;
  bearer_token?: string;
  oauth2?: OAuth2Credentials;
}

export interface ExternalMCPServerCreate {
  name: string;
  display_name: string;
  description?: string;
  icon?: string;
  base_url: string;
  transport: ExternalMCPTransport;
  auth_type: ExternalMCPAuthType;
  credentials?: ExternalMCPServerCredentials;
  tool_prefix?: string;
  tenant_id?: string;
  environment?: string;
  gateway_instance_id?: string;
}

export interface ExternalMCPServerUpdate {
  display_name?: string;
  description?: string;
  icon?: string;
  base_url?: string;
  transport?: ExternalMCPTransport;
  auth_type?: ExternalMCPAuthType;
  credentials?: ExternalMCPServerCredentials;
  tool_prefix?: string;
  enabled?: boolean;
  environment?: string;
  gateway_instance_id?: string;
}

export interface ExternalMCPServerListResponse {
  servers: ExternalMCPServer[];
  total_count: number;
  page: number;
  page_size: number;
}

// Tool Observability types (CAB-1821)
// =============================================================================

export interface ToolObservabilityItem {
  id: string;
  name: string;
  namespaced_name: string;
  display_name?: string;
  description?: string;
  enabled: boolean;
  synced_at: string;
  input_schema?: Record<string, unknown>;
}

export interface ToolsObservabilityResponse {
  server_id: string;
  server_name: string;
  server_display_name: string;
  environment?: string;
  health_status: string;
  last_health_check?: string;
  last_sync_at?: string;
  gateway: Schemas['GatewayBindingInfo'];
  tools: ToolObservabilityItem[];
  tools_count: number;
  enabled_count: number;
}

// Admin Prospects types (CAB-911)
// =============================================================================

export type ProspectStatus = 'pending' | 'opened' | 'converted' | 'expired';
export type NPSCategory = 'promoter' | 'passive' | 'detractor';

export interface ProspectSummary {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  company: string;
  role?: string;
  status: ProspectStatus;
  source?: string;
  created_at: string;
  opened_at?: string;
  last_activity_at?: string;
  time_to_first_tool_seconds?: number;
  nps_score?: number;
  nps_category?: NPSCategory;
  total_events: number;
}

export interface ProspectListMeta {
  total: number;
  page: number;
  limit: number;
}

export interface ProspectListResponse {
  data: ProspectSummary[];
  meta: ProspectListMeta;
}

export interface ProspectEventDetail {
  id: string;
  event_type: string;
  timestamp: string;
  metadata: Record<string, unknown>;
  is_first_tool_call: boolean;
}

export interface ProspectMetrics {
  time_to_open_seconds?: number;
  time_to_first_tool_seconds?: number;
  tools_called_count: number;
  pages_viewed_count: number;
  errors_count: number;
  session_duration_seconds?: number;
}

export interface ProspectDetail {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  company: string;
  role?: string;
  status: ProspectStatus;
  source?: string;
  created_at: string;
  opened_at?: string;
  expires_at: string;
  nps_score?: number;
  nps_category?: NPSCategory;
  nps_comment?: string;
  metrics: ProspectMetrics;
  timeline: ProspectEventDetail[];
  errors: ProspectEventDetail[];
}

export interface ConversionFunnel {
  total_invites: number;
  pending: number;
  opened: number;
  converted: number;
  expired: number;
}

export interface NPSDistribution {
  promoters: number;
  passives: number;
  detractors: number;
  no_response: number;
  nps_score: number;
  avg_score?: number;
}

export interface TimingMetrics {
  avg_time_to_open_seconds?: number;
  avg_time_to_first_tool_seconds?: number;
}

export interface ProspectsMetricsResponse {
  total_invited: number;
  total_active: number;
  avg_time_to_tool?: number;
  avg_nps?: number;
  by_status: ConversionFunnel;
  nps: NPSDistribution;
  timing: TimingMetrics;
  top_companies: Schemas['CompanyStats'][];
}

export interface ProspectsFilters {
  company?: string;
  status?: ProspectStatus;
  date_from?: string;
  date_to?: string;
}

// =============================================================================
// Access Request Types (CAB-1468 — Admin Access Requests)
// =============================================================================

export type AccessRequestStatus = 'pending' | 'contacted' | 'converted';

export interface AccessRequestDetail {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  company?: string;
  role?: string;
  source?: string;
  status: AccessRequestStatus;
  created_at: string;
}

export interface AccessRequestListResponse {
  data: AccessRequestDetail[];
  total: number;
  page: number;
  limit: number;
}

// =============================================================================
// Backend API Types (CAB-1188 — SaaS Self-Service)
// =============================================================================

export type BackendApiAuthType = 'none' | 'api_key' | 'bearer' | 'basic' | 'oauth2_cc';
export type BackendApiStatus = 'draft' | 'active' | 'disabled';

export interface BackendApi {
  id: string;
  tenant_id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  backend_url: string;
  openapi_spec_url: string | null;
  auth_type: BackendApiAuthType;
  has_credentials: boolean;
  status: BackendApiStatus;
  tool_count: number;
  spec_hash: string | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface BackendApiListResponse {
  items: BackendApi[];
  total: number;
  page: number;
  page_size: number;
}

// =============================================================================
// Scoped API Key Types (CAB-1188 — SaaS Self-Service)
// =============================================================================

export type SaasApiKeyStatus = 'active' | 'revoked' | 'expired';

export interface SaasApiKey {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  key_prefix: string;
  allowed_backend_api_ids: string[];
  rate_limit_rpm: number | null;
  status: SaasApiKeyStatus;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  created_by: string | null;
}

export interface SaasApiKeyListResponse {
  items: SaasApiKey[];
  total: number;
  page: number;
  page_size: number;
}

// =============================================================================
// Gateway Instance Types (Control Plane Agnostique)
// =============================================================================

export type GatewayType =
  | 'webmethods'
  | 'kong'
  | 'apigee'
  | 'aws_apigateway'
  | 'stoa'
  | 'stoa_edge_mcp'
  | 'stoa_sidecar'
  | 'stoa_proxy'
  | 'stoa_shadow';
export type GatewayMode = 'edge-mcp' | 'sidecar' | 'proxy' | 'shadow' | 'connect';
export type GatewayInstanceStatus = 'online' | 'offline' | 'degraded' | 'maintenance';
export type DeploymentSyncStatus =
  | 'pending'
  | 'syncing'
  | 'synced'
  | 'drifted'
  | 'error'
  | 'deleting';

// ---- GatewayInstance --------------------------------------------------------
// Wire = `Schemas['GatewayInstanceResponse']`. Post-CAB-2159 the backend
// declares enums + admin fields directly. Only `visibility` keeps a UI narrow:
// backend emits `{ tenant_ids: string[] } | null` but declares the shape as
// `Record<string, unknown> | null` (additionalProperties). Narrow for consumers.
export type GatewayInstance = Omit<Schemas['GatewayInstanceResponse'], 'visibility'> & {
  visibility?: { tenant_ids: string[] } | null;
  deployment_mode?: 'edge' | 'connect' | 'sidecar' | null;
  target_gateway_type?: string | null;
  topology?: 'native-edge' | 'remote-agent' | 'same-pod' | null;
  endpoints?: Record<string, string> | null;
};

export interface GatewayInstanceCreate {
  name: string;
  display_name: string;
  gateway_type: GatewayType;
  environment: string;
  tenant_id?: string;
  base_url: string;
  target_gateway_url?: string;
  public_url?: string;
  ui_url?: string;
  endpoints?: Record<string, string>;
  deployment_mode?: 'edge' | 'connect' | 'sidecar';
  target_gateway_type?: string;
  topology?: 'native-edge' | 'remote-agent' | 'same-pod';
  auth_config?: Record<string, unknown>;
  capabilities?: string[];
  tags?: string[];
}

export interface GatewayInstanceUpdate {
  display_name?: string;
  base_url?: string;
  target_gateway_url?: string;
  public_url?: string;
  ui_url?: string;
  endpoints?: Record<string, string>;
  deployment_mode?: 'edge' | 'connect' | 'sidecar';
  target_gateway_type?: string;
  topology?: 'native-edge' | 'remote-agent' | 'same-pod';
  environment?: string;
  auth_config?: Record<string, unknown>;
  capabilities?: string[];
  tags?: string[];
  enabled?: boolean;
  visibility?: { tenant_ids: string[] } | null;
}

export interface PaginatedGatewayInstances {
  items: GatewayInstance[];
  total: number;
  page: number;
  page_size: number;
}

export interface SyncStep {
  name: string;
  status: 'running' | 'success' | 'failed' | 'skipped';
  started_at: string;
  completed_at?: string;
  detail?: string;
}

// Backend declares `desired_state`/`actual_state` as open objects
// (`Record<string, unknown>`) but the UI reads two well-known keys. Narrow
// with an index signature so typed access works and forward-compat stays.
export interface GatewayDeploymentState {
  api_name?: string;
  tenant_id?: string;
  [key: string]: unknown;
}

// UI `GatewayDeployment` narrows `actual_state` to undefined-only (no null).
// Backend emits `null | undefined | {...}`; the UI reduces that to a simple
// "present or absent" contract for consumers. Normalized at the client edge
// (see `gatewayDeploymentsClient.list` / `.get`).
export interface GatewayDeployment {
  id: string;
  api_catalog_id: string;
  gateway_instance_id: string;
  desired_state: GatewayDeploymentState;
  desired_source?: string;
  git_sync_status?: string;
  desired_commit_sha?: string;
  desired_git_path?: string;
  desired_at: string;
  actual_state?: GatewayDeploymentState;
  actual_at?: string;
  sync_status: DeploymentSyncStatus;
  last_sync_attempt?: string;
  last_sync_success?: string;
  sync_error?: string;
  sync_attempts: number;
  sync_steps?: SyncStep[];
  gateway_resource_id?: string;
  created_at: string;
  updated_at: string;
  gateway_name?: string;
  gateway_display_name?: string;
  gateway_type?: string;
  gateway_environment?: string;
}

// UI paginated wrapper — narrows the Schemas version so consumers receive
// `GatewayDeployment[]` (with UI-narrowed `actual_state`) instead of the
// looser wire shape. Pattern mirrors `PaginatedGatewayInstances`.
export interface PaginatedGatewayDeployments {
  items: GatewayDeployment[];
  total: number;
  page: number;
  page_size: number;
}

// UI summary types for platform dashboards. The backend endpoints
// (`/v1/admin/gateways/health-summary`, `/v1/admin/gateways/modes/stats`)
// are not yet modelled as canonical schemas (returns `unknown`); tracked in
// BACKEND-GAPS-CAB-2159.md §BUG-9.
export interface GatewayHealthSummary {
  online: number;
  offline: number;
  degraded: number;
  maintenance: number;
  total: number;
}

export interface GatewayModeStats {
  modes: Array<{
    mode: string;
    total: number;
    online: number;
    offline: number;
    degraded: number;
  }>;
  total_gateways: number;
}

// =============================================================================
// Gateway Policy Types (Phase 3 — Policy Engine)
// =============================================================================

export type PolicyType =
  | 'cors'
  | 'rate_limit'
  | 'jwt_validation'
  | 'ip_filter'
  | 'logging'
  | 'caching'
  | 'transform';
export type PolicyScope = 'api' | 'gateway' | 'tenant';

export interface GatewayPolicy {
  id: string;
  name: string;
  description?: string;
  policy_type: PolicyType;
  tenant_id?: string;
  scope: PolicyScope;
  config: Record<string, unknown>;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at?: string;
  binding_count: number;
}

// =============================================================================
// Gateway Observability Types (Phase 3 — Metrics)
// =============================================================================

export interface AggregatedMetrics {
  health: {
    total_gateways: number;
    online: number;
    offline: number;
    degraded: number;
    maintenance: number;
    health_percentage: number;
  };
  sync: {
    total_deployments: number;
    synced: number;
    pending: number;
    syncing: number;
    drifted: number;
    error: number;
    deleting: number;
    sync_percentage: number;
  };
  overall_status: string;
  // Guardrails slice is emitted by the metrics endpoint when runtime security
  // features are enabled. Backend does not expose a canonical schema — consumer
  // (`GuardrailsDashboard`) expects this shape (CAB-2164).
  guardrails?: {
    pii_detections?: number;
    injection_blocks?: number;
    content_filters?: number;
    prompt_guard_flags?: number;
    by_tool?: Record<string, number>;
    by_category?: Record<string, number>;
  };
  rate_limiting?: {
    enforcements?: number;
  };
  // TODO(WAVE-2): promote guardrails/rate_limiting to Schemas when backend
  // publishes their shape (see BACKEND-GAPS-CAB-2159.md §BUG-6/BUG-9).
  [key: string]: unknown;
}

// CAB-2164 local wrapper: guardrails event stream consumed by
// `GuardrailsDashboard.tsx`. Backend does not publish a canonical schema —
// these fields reflect the observed runtime contract.
export interface GatewayGuardrailsEvent {
  timestamp: string;
  trace_id: string;
  span_id: string;
  tool: string;
  action: string;
  reason: string;
  [key: string]: unknown;
}

export interface GatewayGuardrailsResponse {
  events: GatewayGuardrailsEvent[];
  total: number;
  // TODO(WAVE-2): replace with Schemas['...'] once backend exposes a canonical
  // guardrails-events schema (see BACKEND-GAPS-CAB-2159.md §BUG-6).
  [key: string]: unknown;
}

// CAB-2164 local wrapper: per-instance metrics mirror the aggregate health
// slice but for a single gateway. Backend endpoint is not yet modelled as a
// canonical schema.
export interface GatewayInstanceMetrics {
  gateway_id: string;
  requests_total?: number;
  errors_total?: number;
  latency_p50_ms?: number;
  latency_p95_ms?: number;
  latency_p99_ms?: number;
  // TODO(WAVE-2): replace with Schemas['GatewayInstanceMetrics'] once backend
  // exposes a canonical schema (see BACKEND-GAPS-CAB-2159.md §BUG-7).
  [key: string]: unknown;
}

// CAB-2164 local wrapper: deployment status summary for admin dashboard.
// Backend returns a status breakdown aggregated across all deployments.
export interface DeploymentStatusSummary {
  total: number;
  synced: number;
  pending: number;
  syncing: number;
  drifted: number;
  error: number;
  deleting: number;
  // TODO(WAVE-2): replace with Schemas['DeploymentStatusSummary'] once backend
  // exposes a canonical schema (see BACKEND-GAPS-CAB-2159.md §BUG-8).
  [key: string]: unknown;
}

// Workflow Engine types (CAB-593)
export type WorkflowType =
  | 'user_registration'
  | 'consumer_registration'
  | 'tenant_owner_onboarding';
export type WorkflowMode = 'auto' | 'manual' | 'approval_chain';
export type WorkflowStatus =
  | 'pending'
  | 'in_progress'
  | 'approved'
  | 'rejected'
  | 'provisioning'
  | 'completed'
  | 'failed';
export type Sector = 'fintech' | 'startup' | 'enterprise';
export type StepAction = 'approved' | 'rejected' | 'skipped';

export interface WorkflowTemplate {
  id: string;
  tenant_id: string;
  workflow_type: WorkflowType;
  mode: WorkflowMode;
  name: string;
  description: string | null;
  approval_steps: Schemas['ApprovalStepDef'][];
  auto_provision: boolean;
  notification_config: Record<string, unknown>;
  sector: Sector | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowTemplateCreate {
  workflow_type: WorkflowType;
  mode: WorkflowMode;
  name: string;
  description?: string | null;
  approval_steps?: Schemas['ApprovalStepDef'][];
  auto_provision?: boolean;
  notification_config?: Record<string, unknown>;
  sector?: Sector | null;
}

export interface WorkflowTemplateUpdate {
  mode?: WorkflowMode;
  name?: string;
  description?: string | null;
  approval_steps?: Schemas['ApprovalStepDef'][];
  auto_provision?: boolean;
  notification_config?: Record<string, unknown>;
  sector?: Sector | null;
  is_active?: boolean;
}

export interface WorkflowInstance {
  id: string;
  template_id: string;
  tenant_id: string;
  subject_id: string;
  subject_email: string;
  workflow_type: WorkflowType;
  status: WorkflowStatus;
  current_step_index: number;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface WorkflowTemplateListResponse {
  items: WorkflowTemplate[];
  total: number;
  page: number;
  page_size: number;
}

export interface WorkflowListResponse {
  items: WorkflowInstance[];
  total: number;
  page: number;
  page_size: number;
}

// =============================================================================
// Federation Types (CAB-1372 — MCP Federation)
// =============================================================================

export type FederationAccountStatus = 'active' | 'suspended' | 'revoked';

export interface MasterAccount {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  status: FederationAccountStatus;
  max_sub_accounts: number;
  sub_account_count: number;
  created_at: string;
  updated_at: string;
}

export interface MasterAccountUpdate {
  name?: string;
  description?: string;
  status?: 'active' | 'suspended';
  max_sub_accounts?: number;
}

export interface MasterAccountListResponse {
  items: MasterAccount[];
  total: number;
  page: number;
  page_size: number;
}

export interface SubAccount {
  id: string;
  master_account_id: string;
  name: string;
  description: string;
  status: FederationAccountStatus;
  api_key_prefix: string;
  allowed_tools: string[];
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
}

export interface SubAccountCreate {
  name: string;
  description?: string;
}

export interface SubAccountCreatedResponse extends SubAccount {
  api_key: string;
}

export interface SubAccountListResponse {
  items: SubAccount[];
  total: number;
  page: number;
  page_size: number;
}

export interface ToolAllowListResponse {
  sub_account_id: string;
  allowed_tools: string[];
}

export interface UsageSubAccountStat {
  sub_account_id: string;
  sub_account_name: string;
  total_requests: number;
  total_tokens: number;
  avg_latency_ms: number;
  error_count: number;
  last_active_at: string | null;
}

export interface UsageResponse {
  master_account_id: string;
  period_days: number;
  total_requests: number;
  total_tokens: number;
  sub_accounts: UsageSubAccountStat[];
}

// CAB-1454: Admin Users Management
export type AdminUserStatus = 'active' | 'suspended' | 'pending';

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  roles: string[];
  tenant_id: string | null;
  tenant_name: string | null;
  status: AdminUserStatus;
  last_login_at: string | null;
  created_at: string;
}

export interface AdminUserListResponse {
  data: AdminUser[];
  total: number;
  page: number;
  limit: number;
}

// CAB-1454: Platform Settings
export type SettingCategory = 'general' | 'security' | 'gateway' | 'notifications';

export interface PlatformSetting {
  key: string;
  value: string;
  category: SettingCategory;
  description: string;
  editable: boolean;
  updated_at: string;
}

export interface PlatformSettingsResponse {
  settings: PlatformSetting[];
  total: number;
}

// CAB-1454: RBAC Role Management
export interface RolePermission {
  name: string;
  description: string;
}

export interface RoleDefinition {
  name: string;
  display_name: string;
  description: string;
  permissions: RolePermission[];
  user_count: number;
}

export interface RoleListResponse {
  roles: RoleDefinition[];
  total: number;
}

// =============================================================================
// MCP Connector Catalog Types (Phase 2 UI)
// =============================================================================

export interface ConnectorTemplate {
  id: string;
  slug: string;
  display_name: string;
  description?: string;
  icon_url?: string;
  category: string;
  mcp_base_url: string;
  transport: string;
  oauth_scopes?: string;
  oauth_pkce_required: boolean;
  documentation_url?: string;
  is_featured: boolean;
  enabled: boolean;
  sort_order: number;
  is_connected: boolean;
  connected_server_id?: string;
  connection_health?: string;
  connected_environment?: string;
  needs_setup: boolean;
}

export interface ConnectorCatalogResponse {
  connectors: ConnectorTemplate[];
  total_count: number;
}

// ============== Subscription Management (CAB-1635) ==============

export type SubscriptionStatus =
  | 'pending'
  | 'active'
  | 'suspended'
  | 'revoked'
  | 'expired'
  | 'rejected';

export interface Subscription {
  id: string;
  application_id: string;
  application_name: string;
  subscriber_id: string;
  subscriber_email: string;
  api_id: string;
  api_name: string;
  api_version: string;
  tenant_id: string;
  plan_id: string | null;
  plan_name: string | null;
  api_key_prefix: string;
  status: SubscriptionStatus;
  status_reason: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  approved_by: string | null;
  revoked_by: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
  provisioning_status: string | null;
  gateway_app_id: string | null;
  provisioning_error: string | null;
}

export interface SubscriptionListResponse {
  items: Subscription[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SubscriptionStats {
  total: number;
  by_status: Record<string, number>;
  by_tenant: Record<string, number>;
  recent_24h: number;
  avg_approval_time_hours: number | null;
}

// ============ Webhook Types (CAB-1647) ============

export type WebhookEventType =
  | 'subscription.created'
  | 'subscription.approved'
  | 'subscription.revoked'
  | 'subscription.key_rotated'
  | 'subscription.expired'
  | '*';

export type WebhookDeliveryStatus = 'pending' | 'success' | 'failed' | 'retrying';

export interface TenantWebhook {
  id: string;
  tenant_id: string;
  name: string;
  url: string;
  events: WebhookEventType[];
  has_secret: boolean;
  headers?: Record<string, string>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  created_by?: string;
}

export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  subscription_id?: string;
  event_type: string;
  payload: Record<string, unknown>;
  status: WebhookDeliveryStatus;
  attempt_count: number;
  max_attempts: number;
  response_status_code?: number;
  response_body?: string;
  error_message?: string;
  created_at: string;
  last_attempt_at?: string;
  next_retry_at?: string;
  delivered_at?: string;
}

export interface WebhookListResponse {
  items: TenantWebhook[];
  total: number;
}

export interface WebhookDeliveryListResponse {
  items: WebhookDelivery[];
  total: number;
}

// ============ Credential Mapping Types (CAB-1648) ============

export type CredentialAuthType = 'api_key' | 'bearer' | 'basic';

export interface CredentialMapping {
  id: string;
  consumer_id: string;
  api_id: string;
  tenant_id: string;
  auth_type: CredentialAuthType;
  header_name: string;
  has_credential: boolean;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface CredentialMappingListResponse {
  items: CredentialMapping[];
  total: number;
  page: number;
  page_size: number;
}

// ============ Contract / UAC Types (CAB-1649) ============

export type ProtocolType = 'rest' | 'mcp' | 'graphql' | 'grpc' | 'kafka';

export type ContractStatus = 'draft' | 'published' | 'deprecated';

export interface ProtocolBinding {
  protocol: ProtocolType;
  enabled: boolean;
  endpoint: string | null;
  playground_url: string | null;
  tool_name: string | null;
  operations: string[];
  proto_file_url: string | null;
  topic_name: string | null;
  traffic_24h: number | null;
}

export interface Contract {
  id: string;
  tenant_id: string;
  name: string;
  display_name: string;
  description: string | null;
  version: string;
  status: ContractStatus;
  openapi_spec_url: string | null;
  bindings: ProtocolBinding[];
  created_at: string;
  updated_at: string;
}

export interface ContractCreate {
  name: string;
  display_name: string;
  description?: string;
  version: string;
  openapi_spec_url?: string;
  status?: ContractStatus;
}

export interface GeneratedBinding {
  protocol: ProtocolType;
  endpoint: string;
  tool_name: string | null;
}

export interface PublishContractResponse {
  contract: Contract;
  bindings_generated: GeneratedBinding[];
}

export interface ContractListResponse {
  items: Contract[];
  total: number;
}

// =============================================================================
// Promotion Types (CAB-1706)
// =============================================================================

export type PromotionStatus = 'pending' | 'promoting' | 'promoted' | 'failed' | 'rolled_back';

export interface Promotion {
  id: string;
  tenant_id: string;
  api_id: string;
  source_environment: string;
  target_environment: string;
  source_deployment_id: string | null;
  target_deployment_id: string | null;
  status: PromotionStatus;
  spec_diff: Record<string, unknown> | null;
  message: string;
  requested_by: string;
  approved_by: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromotionListResponse {
  items: Promotion[];
  total: number;
  page: number;
  page_size: number;
}

// ─── EU API Catalog (CAB-1639) ────────────────────────────────────────────────

export interface CatalogTool {
  name: string;
  description?: string;
}

export interface CatalogEntry {
  id: string;
  name: string;
  display_name: string;
  description: string;
  category: string;
  country: string;
  region: string;
  spec_url?: string;
  mcp_endpoint?: string;
  protocol: 'openapi' | 'mcp' | 'graphql';
  auth_type: 'none' | 'api_key' | 'oauth2' | 'basic';
  tools: CatalogTool[];
  status: 'verified' | 'community' | 'experimental';
  tags: string[];
  documentation_url?: string;
  icon?: string;
}

export interface CatalogCategory {
  id: string;
  name: string;
  icon?: string;
}

export interface CatalogResponse {
  entries: CatalogEntry[];
  total: number;
  categories: CatalogCategory[];
}

// Tenant Tool Permissions (CAB-1982)
// =============================================================================

export interface TenantToolPermission {
  id: string;
  tenant_id: string;
  mcp_server_id: string;
  tool_name: string;
  allowed: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface TenantToolPermissionListResponse {
  items: TenantToolPermission[];
  total: number;
  page: number;
  page_size: number;
}
