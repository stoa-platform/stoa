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
}

// MCP Tool types
export interface MCPTool {
  id: string;
  name: string;
  displayName: string;
  description: string;
  version: string;
  category?: string;
  tags?: string[];
  endpoint: string;
  method: string;
  inputSchema?: object;
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
  status: 'active' | 'deprecated' | 'beta';
  createdAt: string;
  updatedAt: string;
}

// Subscription types
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
