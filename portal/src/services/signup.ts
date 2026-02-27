/**
 * STOA Developer Portal — Self-Service Signup (CAB-1548)
 *
 * Public API client for tenant provisioning. Uses a separate axios instance
 * WITHOUT auth interceptor — signup is accessible to unauthenticated users.
 */

import axios from 'axios';
import { config } from '../config';

// Separate client without auth interceptor — signup is public
const publicClient = axios.create({
  baseURL: config.api.baseUrl,
  timeout: config.api.timeout,
  headers: { 'Content-Type': 'application/json' },
});

// ============ Types ============

export interface SignupRequest {
  name: string;
  display_name: string;
  owner_email: string;
  company?: string;
  plan: 'trial' | 'standard';
  invite_code?: string;
}

export interface SignupResponse {
  tenant_id: string;
  status: string;
  plan: string;
  poll_url: string;
}

export interface SignupStatusResponse {
  tenant_id: string;
  provisioning_status: string;
  plan: string | null;
  ready_at: string | null;
}

// ============ Service ============

export const signupService = {
  /**
   * Create a new tenant via self-service signup
   * POST /v1/self-service/tenants (rate-limited 5/min)
   */
  signup: async (data: SignupRequest): Promise<SignupResponse> => {
    const response = await publicClient.post<SignupResponse>('/v1/self-service/tenants', data);
    return response.data;
  },

  /**
   * Poll provisioning status
   * GET /v1/self-service/tenants/{tenantId}/status (rate-limited 30/min)
   */
  getStatus: async (tenantId: string): Promise<SignupStatusResponse> => {
    const response = await publicClient.get<SignupStatusResponse>(
      `/v1/self-service/tenants/${tenantId}/status`
    );
    return response.data;
  },
};

export default signupService;
