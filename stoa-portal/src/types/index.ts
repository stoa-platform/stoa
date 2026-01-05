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

// API Catalog types (future)
export interface API {
  id: string;
  name: string;
  version: string;
  description: string;
  category?: string;
  documentation?: string;
  status: 'published' | 'deprecated' | 'beta';
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
