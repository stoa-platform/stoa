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
