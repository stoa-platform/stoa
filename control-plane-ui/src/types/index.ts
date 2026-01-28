// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
// User and Auth types
export interface User {
  id: string;
  email: string;
  name: string;
  roles: string[];
  tenant_id?: string;
  permissions: string[];
}

export type Role = 'cpi-admin' | 'tenant-admin' | 'devops' | 'viewer';

export interface Permission {
  name: string;
  description: string;
}

// Tenant types
export interface Tenant {
  id: string;
  name: string;
  display_name: string;
  status: 'active' | 'suspended' | 'pending';
  created_at: string;
  updated_at: string;
}

export interface TenantCreate {
  name: string;
  display_name: string;
}

// API types
export interface API {
  id: string;
  tenant_id: string;
  name: string;
  display_name: string;
  version: string;
  description: string;
  backend_url: string;
  status: 'draft' | 'published' | 'deprecated';
  deployed_dev: boolean;
  deployed_staging: boolean;
  tags?: string[];
  portal_promoted?: boolean; // Whether API is promoted to Developer Portal
  created_at: string;
  updated_at: string;
}

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

// Application types
export interface Application {
  id: string;
  tenant_id: string;
  name: string;
  display_name: string;
  description: string;
  client_id: string;
  status: 'pending' | 'approved' | 'suspended';
  api_subscriptions: string[];
  created_at: string;
  updated_at: string;
}

export interface ApplicationCreate {
  name: string;
  display_name: string;
  description: string;
  redirect_uris: string[];
  api_subscriptions: string[];
}

// Deployment types
export type Environment = 'dev' | 'staging';
export type DeploymentStatus = 'pending' | 'in_progress' | 'success' | 'failed' | 'rolled_back';

export interface Deployment {
  id: string;
  tenant_id: string;
  api_id: string;
  api_name: string;
  environment: Environment;
  version: string;
  status: DeploymentStatus;
  started_at: string;
  completed_at?: string;
  deployed_by: string;
  awx_job_id?: string;
  error_message?: string;
}

export interface DeploymentRequest {
  api_id: string;
  environment: Environment;
  version?: string;
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
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  tags: string[];
  version: string;
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

// MCP Error Snapshot types (Phase 4)
export type MCPErrorType =
  | 'server_timeout'
  | 'server_unavailable'
  | 'server_rate_limited'
  | 'server_auth_failure'
  | 'server_internal_error'
  | 'tool_not_found'
  | 'tool_execution_error'
  | 'tool_validation_error'
  | 'tool_timeout'
  | 'llm_context_exceeded'
  | 'llm_content_filtered'
  | 'llm_quota_exceeded'
  | 'llm_rate_limited'
  | 'llm_invalid_request'
  | 'policy_denied'
  | 'policy_error'
  | 'unknown';

export type SnapshotResolutionStatus = 'unresolved' | 'investigating' | 'resolved' | 'ignored';

export interface MCPServerContext {
  name: string;
  url?: string;
  version?: string;
  tools_available: string[];
  health_at_error?: string;
  latency_p99_ms?: number;
  error_rate_percent?: number;
}

export interface ToolInvocation {
  tool_name: string;
  input_params?: Record<string, unknown>;
  input_params_masked?: string[];
  started_at?: string;
  duration_ms?: number;
  error_type?: string;
  error_message?: string;
  error_retryable?: boolean;
  backend_status_code?: number;
  backend_response_preview?: string;
}

export interface LLMContext {
  provider: string;
  model: string;
  tokens_input: number;
  tokens_output: number;
  estimated_cost_usd: number;
  latency_ms: number;
  error_code?: string;
  prompt_length?: number;
  prompt_hash?: string;
}

export interface RetryContext {
  attempts: number;
  max_attempts: number;
  strategy: string;
  delays_ms?: number[];
  fallback_attempted: boolean;
  fallback_server?: string;
  fallback_result?: string;
}

export interface RequestContext {
  method: string;
  path: string;
  query_params?: Record<string, string>;
  headers?: Record<string, string>;
  client_ip?: string;
  user_agent?: string;
}

export interface UserContext {
  user_id?: string;
  tenant_id?: string;
  client_id?: string;
  roles?: string[];
  scopes?: string[];
}

export interface MCPErrorSnapshotSummary {
  id: string;
  timestamp: string;
  error_type: MCPErrorType;
  error_message: string;
  response_status: number;
  mcp_server_name?: string;
  tool_name?: string;
  total_cost_usd: number;
  tokens_wasted: number;
  resolution_status: SnapshotResolutionStatus;
}

export interface MCPErrorSnapshot {
  id: string;
  timestamp: string;
  error_type: MCPErrorType;
  error_message: string;
  error_code?: string;
  response_status: number;
  request_method?: string;
  request_path?: string;
  user_id?: string;
  tenant_id?: string;
  mcp_server_name?: string;
  tool_name?: string;
  llm_provider?: string;
  llm_model?: string;
  llm_tokens_input?: number;
  llm_tokens_output?: number;
  total_cost_usd: number;
  tokens_wasted: number;
  retry_attempts: number;
  retry_max_attempts: number;
  trace_id?: string;
  conversation_id?: string;
  resolution_status: SnapshotResolutionStatus;
  resolution_notes?: string;
  resolved_at?: string;
  resolved_by?: string;
  snapshot: {
    request?: RequestContext;
    user?: UserContext;
    mcp_server?: MCPServerContext;
    tool_invocation?: ToolInvocation;
    llm_context?: LLMContext;
    retry_context?: RetryContext;
    masked_fields?: string[];
    [key: string]: unknown;
  };
}

export interface MCPErrorSnapshotStats {
  total: number;
  by_error_type: Record<string, number>;
  by_status: Record<number, number>;
  by_server: Record<string, number>;
  total_cost_usd: number;
  total_tokens_wasted: number;
  avg_cost_usd: number;
  resolution_stats: {
    unresolved: number;
    investigating: number;
    resolved: number;
    ignored: number;
  };
}

export interface MCPErrorSnapshotFilters {
  error_types?: MCPErrorType[];
  status_codes?: number[];
  server_names?: string[];
  tool_names?: string[];
  resolution_status?: SnapshotResolutionStatus[];
  start_date?: string;
  end_date?: string;
  min_cost_usd?: number;
  search?: string;
}

export interface MCPErrorSnapshotListResponse {
  snapshots: MCPErrorSnapshotSummary[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface SnapshotFiltersResponse {
  error_types: string[];
  servers: string[];
  tools: string[];
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
  started_at: string;
  duration_ms: number;
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
  client_ip?: string;
  user_id?: string;
  started_at: string;
  total_duration_ms: number;
  spans: TransactionSpan[];
  request_headers?: Record<string, string>;
  response_headers?: Record<string, string>;
  error_message?: string;
}

export interface APITransactionSummary {
  id: string;
  trace_id: string;
  api_name: string;
  method: string;
  path: string;
  status_code: number;
  status: TransactionStatus;
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
  by_api: Record<string, {
    total: number;
    success: number;
    errors: number;
    avg_latency_ms: number;
  }>;
  by_status_code: Record<number, number>;
}

// =============================================================================
// Platform Status types (CAB-654 - GitOps Observability)
// =============================================================================

export type ComponentHealth = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
export type GitOpsSyncStatus = 'Synced' | 'OutOfSync' | 'Unknown' | 'NotFound' | 'Error';
export type GitOpsHealthStatus = 'Healthy' | 'Degraded' | 'Progressing' | 'Suspended' | 'Missing' | 'Unknown';
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

export interface SyncResponse {
  message: string;
  operation: string | null;
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
  health_status: ExternalMCPHealthStatus;
  last_health_check?: string;
  last_sync_at?: string;
  sync_error?: string;
  tenant_id?: string;
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
}

export interface ExternalMCPServerListResponse {
  servers: ExternalMCPServer[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface TestConnectionResponse {
  success: boolean;
  latency_ms?: number;
  error?: string;
  server_info?: Record<string, unknown>;
  tools_discovered?: number;
}

export interface SyncToolsResponse {
  synced_count: number;
  removed_count: number;
  tools: ExternalMCPServerTool[];
}

// Admin Prospects types (CAB-911)
// =============================================================================

export type ProspectStatus = 'pending' | 'opened' | 'converted' | 'expired';
export type NPSCategory = 'promoter' | 'passive' | 'detractor';

export interface ProspectSummary {
  id: string;
  email: string;
  company: string;
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
  company: string;
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

export interface CompanyStats {
  company: string;
  invite_count: number;
  converted_count: number;
}

export interface ProspectsMetricsResponse {
  total_invited: number;
  total_active: number;
  avg_time_to_tool?: number;
  avg_nps?: number;
  by_status: ConversionFunnel;
  nps: NPSDistribution;
  timing: TimingMetrics;
  top_companies: CompanyStats[];
}

export interface ProspectsFilters {
  company?: string;
  status?: ProspectStatus;
  date_from?: string;
  date_to?: string;
}
