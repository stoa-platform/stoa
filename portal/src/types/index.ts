/**
 * Type definitions for STOA Developer Portal
 */

// User type (simplified for portal - consumers only)
export interface User {
  id: string;
  email: string;
  name: string;
  tenant_id?: string;
  organization?: string;
  roles?: string[];
  is_admin?: boolean;
}

// MCP Tool types (aligned with MCP Gateway response format)
export interface MCPTool {
  name: string;              // Tool identifier (e.g., "tenant-acme__create-order")
  displayName?: string;      // Human-friendly name
  description: string;
  tags?: string[];           // Categories/tags for filtering
  tenant_id?: string;        // Owning tenant
  inputSchema?: MCPInputSchema;  // JSON Schema for tool arguments
  // Legacy fields for backward compatibility
  id?: string;
  version?: string;
  category?: string;
  endpoint?: string;
  method?: string;
  outputSchema?: object;
  rateLimit?: {
    requests: number;
    period: string;
  };
  pricing?: {
    model: 'free' | 'per-call' | 'subscription';
    pricePerCall?: number;
    currency?: string;
  };
  status?: 'active' | 'deprecated' | 'beta';
  createdAt?: string;
  updatedAt?: string;
}

// MCP Input Schema (JSON Schema format)
export interface MCPInputSchema {
  type: 'object';
  properties?: Record<string, MCPPropertySchema>;
  required?: string[];
  additionalProperties?: boolean;
}

export interface MCPPropertySchema {
  type: string;
  description?: string;
  enum?: string[];
  default?: unknown;
  format?: string;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  items?: MCPPropertySchema;
  properties?: Record<string, MCPPropertySchema>;  // For nested objects
  required?: string[];                             // For nested object required fields
}

// MCP Tool invocation result
export interface MCPToolInvocation {
  toolName: string;
  status: 'success' | 'error';
  result?: unknown;
  error?: {
    code: string;
    message: string;
    details?: unknown;
  };
  executionTimeMs: number;
  timestamp: string;
}

// MCP Server Info
export interface MCPServerInfo {
  name: string;
  version: string;
  protocolVersion?: string;
  capabilities?: {
    tools?: boolean;
    resources?: boolean;
    prompts?: boolean;
  };
}

// ============ MCP Subscription types (CAB-247) ============
// MCP Subscriptions are on MCP Gateway, NOT Control-Plane API!

export interface MCPSubscription {
  id: string;
  tenant_id: string;
  user_id: string;
  tool_id: string;
  status: 'active' | 'expired' | 'revoked';
  plan: string;
  created_at: string;
  expires_at: string | null;
  last_used_at?: string;
  usage_count?: number;
  api_key_prefix?: string;  // First 12 chars for display (e.g., "stoa_sk_XXXX")
  totp_required?: boolean;  // Whether 2FA is required to reveal the API key
  // Key rotation fields (CAB-314)
  previous_key_expires_at?: string | null;  // Grace period expiry
  last_rotated_at?: string | null;          // Last rotation timestamp
  rotation_count?: number;                   // Number of rotations
  has_active_grace_period?: boolean;        // True if grace period is active
}

// Key Rotation types (CAB-314)
export interface KeyRotationRequest {
  grace_period_hours?: number;  // Default: 24, range: 1-168
}

export interface KeyRotationResponse {
  subscription_id: string;
  new_api_key: string;           // Shown only ONCE!
  new_api_key_prefix: string;
  old_key_expires_at: string;    // ISO datetime
  grace_period_hours: number;
  rotation_count: number;
}

export interface MCPSubscriptionCreate {
  tool_id: string;
  plan?: 'free' | 'basic' | 'premium';
  tenant_id?: string; // Optional, derived from JWT if not provided
}

export interface MCPSubscriptionConfig {
  mcpServers: {
    [key: string]: {
      command: string;
      args: string[];
      env: {
        STOA_API_KEY: string;
      };
    };
  };
}

// Subscription types (legacy - for backward compatibility)
export interface Subscription {
  id: string;
  userId: string;
  toolId: string;
  tool?: MCPTool;
  status: 'active' | 'pending' | 'cancelled' | 'expired';
  plan: 'free' | 'basic' | 'premium';
  createdAt: string;
  expiresAt?: string;
  usage?: SubscriptionUsage;
}

export interface SubscriptionUsage {
  callsToday: number;
  callsThisMonth: number;
  dailyLimit: number;
  monthlyLimit: number;
}

// API Catalog types
export interface API {
  id: string;
  name: string;
  version: string;
  description: string;
  category?: string;
  tags?: string[];
  tenantId: string;
  tenantName?: string;
  documentation?: string;
  openApiSpec?: object;
  endpoints?: APIEndpoint[];
  status: 'draft' | 'published' | 'deprecated';
  createdAt: string;
  updatedAt: string;
}

export interface APIEndpoint {
  path: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  summary: string;
  description?: string;
  parameters?: APIParameter[];
  requestBody?: APIRequestBody;
  responses?: Record<string, APIResponse>;
}

export interface APIParameter {
  name: string;
  in: 'query' | 'path' | 'header' | 'cookie';
  required: boolean;
  schema?: object;
  description?: string;
}

export interface APIRequestBody {
  required: boolean;
  content: Record<string, { schema: object }>;
  description?: string;
}

export interface APIResponse {
  description: string;
  content?: Record<string, { schema: object }>;
}

// Consumer Application types
export interface Application {
  id: string;
  name: string;
  description?: string;
  clientId: string;
  clientSecret?: string; // Only shown on creation or regeneration
  callbackUrls: string[];
  userId: string;
  status: 'active' | 'suspended' | 'deleted';
  subscriptions?: APISubscription[];
  createdAt: string;
  updatedAt: string;
}

export interface ApplicationCreateRequest {
  name: string;
  description?: string;
  callbackUrls: string[];
}

// API Subscription types (for consumer apps)
export interface APISubscription {
  id: string;
  applicationId: string;
  application?: Application;
  apiId: string;
  api?: API;
  status: 'pending' | 'active' | 'suspended' | 'cancelled';
  plan: 'free' | 'basic' | 'premium' | 'enterprise';
  rateLimit?: {
    requests: number;
    period: string;
  };
  usage?: APISubscriptionUsage;
  createdAt: string;
  expiresAt?: string;
}

export interface APISubscriptionUsage {
  callsToday: number;
  callsThisMonth: number;
  dailyLimit: number;
  monthlyLimit: number;
  lastCallAt?: string;
}

// Environment types
export interface Environment {
  id: string;
  name: string;           // dev, staging1, staging2, prod
  displayName: string;    // Development, Staging 1, Production
  type: 'development' | 'staging' | 'production';
  baseUrl: string;
  isProduction: boolean;
}

// API Testing types
export interface APITestRequest {
  method: string;
  path: string;
  headers: Record<string, string>;
  queryParams?: Record<string, string>;
  body?: string;
  environment: string;
}

export interface APITestResponse {
  status: number;
  statusText: string;
  headers: Record<string, string>;
  body: string;
  timing: {
    total: number;
    dns?: number;
    connect?: number;
    ttfb?: number;
  };
  requestedAt: string;
}

// Common types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface ApiError {
  message: string;
  code?: string;
  details?: Record<string, unknown>;
}

// ============ Webhook Types (CAB-315) ============

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

export interface WebhookCreate {
  name: string;
  url: string;
  events: WebhookEventType[];
  secret?: string;
  headers?: Record<string, string>;
}

export interface WebhookUpdate {
  name?: string;
  url?: string;
  events?: WebhookEventType[];
  secret?: string;
  headers?: Record<string, string>;
  enabled?: boolean;
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

export interface WebhookTestResponse {
  success: boolean;
  status_code?: number;
  response_body?: string;
  error?: string;
  signature_header?: string;
}
