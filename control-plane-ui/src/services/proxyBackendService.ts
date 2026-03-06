/**
 * Proxy Backend Service (CAB-1727)
 *
 * Client for platform-level proxy backend management (cpi-admin).
 * These are the internal APIs that the STOA Gateway proxies.
 */

import { apiService } from './api';

export interface ProxyBackendResponse {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  base_url: string;
  health_endpoint: string | null;
  auth_type: 'api_key' | 'bearer' | 'basic' | 'oauth2_cc';
  credential_ref: string | null;
  rate_limit_rpm: number;
  circuit_breaker_enabled: boolean;
  fallback_direct: boolean;
  timeout_secs: number;
  status: 'active' | 'disabled';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProxyBackendListResponse {
  items: ProxyBackendResponse[];
  total: number;
}

export interface ProxyBackendHealthStatus {
  backend_name: string;
  healthy: boolean;
  status_code: number | null;
  latency_ms: number | null;
  error: string | null;
  checked_at: string;
}

class ProxyBackendService {
  async list(activeOnly = false): Promise<ProxyBackendListResponse> {
    const { data } = await apiService.get('/v1/proxy-backends', {
      params: { active_only: activeOnly },
    });
    return data;
  }

  async healthCheck(backendId: string): Promise<ProxyBackendHealthStatus> {
    const { data } = await apiService.get(`/v1/proxy-backends/${backendId}/health`);
    return data;
  }
}

export const proxyBackendService = new ProxyBackendService();
