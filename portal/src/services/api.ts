/**
 * STOA Developer Portal - API Client
 *
 * Axios instance with authentication interceptor for Control Plane API calls.
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import { config } from '../config';
import { getFriendlyErrorMessage } from '@stoa/shared/utils';

// Dynamic base URL — updated by EnvironmentContext on env switch
let currentBaseUrl: string = config.api.baseUrl;

/**
 * Update the API base URL (called by EnvironmentContext on environment switch)
 */
export function setApiBaseUrl(url: string) {
  currentBaseUrl = url;
}

/**
 * Get the current API base URL
 */
export function getApiBaseUrl(): string {
  return currentBaseUrl;
}

// Create axios instance with base configuration
export const apiClient: AxiosInstance = axios.create({
  baseURL: config.api.baseUrl,
  timeout: config.api.timeout,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token storage - will be set by AuthContext
let accessToken: string | null = null;

/**
 * Set the access token for API calls
 * Called by AuthContext when user authenticates
 */
export function setAccessToken(token: string | null) {
  accessToken = token;
}

/**
 * Get the current access token
 */
export function getAccessToken(): string | null {
  return accessToken;
}

// Request interceptor - sets dynamic baseURL and adds Authorization header
apiClient.interceptors.request.use(
  (config) => {
    config.baseURL = currentBaseUrl;
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - handle errors globally
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Handle specific error cases
    if (error.response) {
      const url = error.config?.url || '';
      switch (error.response.status) {
        case 401:
          // Token expired or invalid - could trigger re-auth
          console.warn('API: Unauthorized - token may be expired');
          break;
        case 403:
          console.warn('API: Forbidden - insufficient permissions');
          break;
        case 404:
          // Silence 404 for optional endpoints (not yet implemented in CP API)
          if (!url.includes('/portal/notifications') && !url.includes('/portal/favorites')) {
            console.warn('API: Resource not found');
          }
          break;
        case 500:
          console.error('API: Server error');
          break;
        default:
          console.error('API: Request failed', error.response.status);
      }
    } else if (error.request) {
      console.error('API: No response received', error.message);
    } else {
      console.error('API: Request setup error', error.message);
    }
    // CAB-1629: Replace raw HTTP status messages with user-friendly ones
    if (error instanceof Error) {
      error.message = getFriendlyErrorMessage(error, error.message);
    }
    return Promise.reject(error);
  }
);

/**
 * Create a new chat conversation for the given tenant
 */
export async function createChatConversation(
  tenantId: string,
  title = 'New conversation'
): Promise<{ id: string }> {
  const { data } = await apiClient.post(`/v1/tenants/${tenantId}/chat/conversations`, { title });
  return data;
}

// Chat Settings (CAB-1853)
export interface TenantChatSettings {
  chat_console_enabled: boolean;
  chat_portal_enabled: boolean;
  chat_daily_budget: number;
}

export async function getChatSettings(tenantId: string): Promise<TenantChatSettings> {
  const { data } = await apiClient.get(`/v1/tenants/${tenantId}/chat/settings`);
  return data;
}

export async function updateChatSettings(
  tenantId: string,
  settings: Partial<TenantChatSettings>
): Promise<TenantChatSettings> {
  const { data } = await apiClient.put(`/v1/tenants/${tenantId}/chat/settings`, settings);
  return data;
}

export default apiClient;
