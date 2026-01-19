/**
 * Type definitions for STOA Developer Portal
 */

// User type with RBAC support
export interface User {
  id: string;
  email: string;
  name: string;
  tenant_id?: string;
  organization?: string;
  roles: string[];
  permissions: string[];
  effective_scopes: string[];
  is_admin?: boolean;
}

// Response from /v1/me endpoint (single source of truth)
export interface UserPermissionsResponse {
  user_id: string;
  email: string;
  username: string;
  tenant_id: string | null;
  roles: string[];
  permissions: string[];
  effective_scopes: string[];
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
  applicationName?: string;
  application?: Application;
  apiId: string;
  apiName?: string;
  apiVersion?: string;
  api?: API;
  tenantId?: string;
  planId?: string;
  planName?: string;
  status: 'pending' | 'active' | 'suspended' | 'cancelled' | 'revoked' | 'expired';
  plan?: 'free' | 'basic' | 'premium' | 'enterprise';
  apiKeyPrefix?: string;
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

// ============ Usage Dashboard Types (CAB-280) ============

export type UsageCallStatus = 'success' | 'error' | 'timeout';

export interface UsagePeriodStats {
  period: string;
  total_calls: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  avg_latency_ms: number;
}

export interface ToolUsageStat {
  tool_id: string;
  tool_name: string;
  call_count: number;
  success_rate: number;
  avg_latency_ms: number;
}

export interface DailyCallStat {
  date: string;
  calls: number;
}

export interface UsageSummary {
  tenant_id: string;
  user_id: string;
  today: UsagePeriodStats;
  this_week: UsagePeriodStats;
  this_month: UsagePeriodStats;
  top_tools: ToolUsageStat[];
  daily_calls: DailyCallStat[];
}

export interface UsageCall {
  id: string;
  timestamp: string;
  tool_id: string;
  tool_name: string;
  status: UsageCallStatus;
  latency_ms: number;
  error_message?: string | null;
}

export interface UsageCallsResponse {
  calls: UsageCall[];
  total: number;
  limit: number;
  offset: number;
}

export interface UsageCallsParams {
  limit?: number;
  offset?: number;
  status?: UsageCallStatus;
  tool_id?: string;
  from_date?: string;
  to_date?: string;
}

export interface ActiveSubscription {
  id: string;
  tool_id: string;
  tool_name: string;
  tool_description?: string | null;
  status: string;
  created_at: string;
  last_used_at?: string | null;
  call_count_total: number;
}

// ============ Dashboard Types (CAB-299) ============

export type ActivityType =
  | 'subscription.created'
  | 'subscription.approved'
  | 'subscription.revoked'
  | 'api.call'
  | 'key.rotated';

export interface DashboardStats {
  tools_available: number;
  active_subscriptions: number;
  api_calls_this_week: number;
  // Optional trends
  tools_trend?: number;        // % change
  subscriptions_trend?: number;
  calls_trend?: number;
}

export interface RecentActivityItem {
  id: string;
  type: ActivityType;
  title: string;
  description?: string;
  tool_id?: string;
  tool_name?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface DashboardData {
  stats: DashboardStats;
  recent_activity: RecentActivityItem[];
}

// ============ MCP Server Types (CAB-xxx - Server-based Subscriptions) ============

/**
 * Visibility configuration for MCP Servers
 * Controls which roles can see and subscribe to a server
 */
export interface MCPServerVisibility {
  roles?: string[];           // Required roles to see this server (e.g., ['cpi-admin', 'tenant-admin'])
  excludeRoles?: string[];    // Roles that cannot see this server
  public?: boolean;           // If true, visible to all authenticated users
}

/**
 * MCP Server represents a collection of related tools
 * Examples: "STOA Platform", "CRM APIs", "Billing Services"
 */
export interface MCPServer {
  id: string;
  name: string;                    // Unique identifier (e.g., "stoa-platform")
  displayName: string;             // Human-friendly name
  description: string;
  icon?: string;                   // Icon name or URL
  category: 'platform' | 'tenant' | 'public';  // Server category
  tenant_id?: string;              // Owning tenant (for tenant servers)
  visibility: MCPServerVisibility;
  tools: MCPServerTool[];          // Tools in this server
  status: 'active' | 'maintenance' | 'deprecated';
  version?: string;
  documentation_url?: string;
  created_at: string;
  updated_at: string;
}

/**
 * Tool within an MCP Server (lighter than full MCPTool)
 */
export interface MCPServerTool {
  id: string;
  name: string;
  displayName: string;
  description: string;
  inputSchema?: MCPInputSchema;
  enabled: boolean;                // Whether this tool is enabled in the server
  requires_approval?: boolean;     // Admin approval needed for this tool
}

/**
 * Server subscription - subscribes to an entire server, with per-tool access control
 */
export interface MCPServerSubscription {
  id: string;
  server_id: string;
  server: MCPServer;
  tenant_id: string;
  user_id: string;
  status: 'pending' | 'active' | 'suspended' | 'revoked';
  plan: 'free' | 'basic' | 'premium';

  // Per-tool access within the subscription
  tool_access: MCPToolAccess[];

  // API key for this server subscription
  api_key_prefix?: string;
  totp_required?: boolean;

  // Key rotation
  last_rotated_at?: string | null;
  has_active_grace_period?: boolean;

  created_at: string;
  expires_at?: string | null;
  last_used_at?: string;
}

/**
 * Per-tool access control within a server subscription
 */
export interface MCPToolAccess {
  tool_id: string;
  tool_name: string;
  status: 'enabled' | 'disabled' | 'pending_approval';
  granted_at?: string;
  granted_by?: string;  // Admin who approved
}

/**
 * Request to create a server subscription
 */
export interface MCPServerSubscriptionCreate {
  server_id: string;
  plan?: 'free' | 'basic' | 'premium';
  requested_tools: string[];   // Tool IDs to request access to
}

/**
 * Server subscription with full API key (shown only on creation)
 */
export interface MCPServerSubscriptionWithKey extends MCPServerSubscription {
  api_key: string;  // Full key, shown only once!
}

// ============ UAC Contract & Protocol Binding Types ============

/**
 * Supported protocol types for UAC bindings
 */
export type ProtocolType = 'rest' | 'graphql' | 'grpc' | 'mcp' | 'kafka';

/**
 * Contract lifecycle status
 */
export type ContractStatus = 'draft' | 'published' | 'deprecated';

/**
 * Protocol binding for a contract
 * Represents whether a protocol (REST, MCP, etc.) is enabled for a contract
 */
export interface ProtocolBinding {
  protocol: ProtocolType;
  enabled: boolean;
  endpoint?: string;
  playground_url?: string;
  tool_name?: string;           // For MCP
  operations?: string[];        // For GraphQL
  proto_file_url?: string;      // For gRPC
  topic_name?: string;          // For Kafka
  traffic_24h?: number;         // Request count in last 24 hours
  generated_at?: string;
  generation_error?: string;
}

/**
 * Universal API Contract
 * A contract defines an API once and can expose it via multiple protocols
 */
export interface Contract {
  id: string;
  tenant_id: string;
  name: string;
  display_name?: string;
  description?: string;
  version: string;
  status: ContractStatus;
  openapi_spec_url?: string;
  created_at: string;
  updated_at: string;
  created_by?: string;
  bindings: ProtocolBinding[];
}

/**
 * Response for listing bindings
 */
export interface BindingsListResponse {
  contract_id: string;
  contract_name: string;
  bindings: ProtocolBinding[];
}

/**
 * Request to enable a protocol binding
 */
export interface EnableBindingRequest {
  protocol: ProtocolType;
}

/**
 * Response after enabling a protocol binding
 */
export interface EnableBindingResponse {
  protocol: ProtocolType;
  endpoint: string;
  playground_url?: string;
  tool_name?: string;
  status: 'active';
  generated_at: string;
}

/**
 * Response after disabling a protocol binding
 */
export interface DisableBindingResponse {
  protocol: ProtocolType;
  status: 'disabled';
  disabled_at: string;
}

/**
 * Request to create a new contract
 */
export interface ContractCreate {
  name: string;
  display_name?: string;
  description?: string;
  version?: string;
  openapi_spec_url?: string;
}

/**
 * Paginated list of contracts
 */
export interface ContractListResponse {
  items: Contract[];
  total: number;
  page: number;
  page_size: number;
}

// ============ Publish Contract Response Types (CAB-560) ============

/**
 * Status of an auto-generated binding after contract publication
 */
export type BindingStatus = 'created' | 'available' | 'disabled';

/**
 * Generated binding info returned after contract publication
 */
export interface GeneratedBinding {
  protocol: ProtocolType;
  status: BindingStatus;
  endpoint?: string;
  playground_url?: string;
  tool_name?: string;           // For MCP
  operations?: string[];        // For GraphQL
  auto_generated?: boolean;     // True for auto-enabled bindings (e.g., MCP)
}

/**
 * Enriched response after publishing/creating a contract
 * Shows all auto-generated bindings for the "wow" effect
 */
export interface PublishContractResponse {
  id: string;
  name: string;
  version: string;
  status: ContractStatus;
  bindings_generated: GeneratedBinding[];
  created_at: string;
  updated_at: string;
}
