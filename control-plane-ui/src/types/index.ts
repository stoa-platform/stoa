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
