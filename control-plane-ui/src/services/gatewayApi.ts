import { apiService } from './api';

export interface GatewayHealthResponse {
  status: 'healthy' | 'unhealthy';
  proxy_mode: boolean;
  proxy_url?: string | null;
  gateway_health?: unknown;
  error?: string;
}

export interface GatewayAPIResponse {
  id: string;
  apiName: string;
  apiVersion: string;
  type?: string | null;
  isActive: boolean;
  systemVersion?: number | null;
}

export interface GatewayApplicationResponse {
  id: string;
  name: string;
  description?: string | null;
  contactEmails: string[];
}

export interface GatewayStatusResponse {
  health: GatewayHealthResponse;
  apis: GatewayAPIResponse[];
  applications: GatewayApplicationResponse[];
  fetchedAt: string;
}

export async function getGatewayHealth(): Promise<GatewayHealthResponse> {
  const { data } = await apiService.get<GatewayHealthResponse>('/v1/gateway/health');
  return data;
}

export async function getGatewayAPIs(): Promise<GatewayAPIResponse[]> {
  const { data } = await apiService.get<GatewayAPIResponse[]>('/v1/gateway/apis');
  return data;
}

export async function getGatewayApplications(): Promise<GatewayApplicationResponse[]> {
  const { data } = await apiService.get<GatewayApplicationResponse[]>('/v1/gateway/applications');
  return data;
}

export async function getGatewayStatus(): Promise<GatewayStatusResponse> {
  const [healthResult, apisResult, appsResult] = await Promise.allSettled([
    getGatewayHealth(),
    getGatewayAPIs(),
    getGatewayApplications(),
  ]);

  const health: GatewayHealthResponse = healthResult.status === 'fulfilled'
    ? healthResult.value
    : { status: 'unhealthy', proxy_mode: false, error: String((healthResult as PromiseRejectedResult).reason) };

  return {
    health,
    apis: apisResult.status === 'fulfilled' ? apisResult.value : [],
    applications: appsResult.status === 'fulfilled' ? appsResult.value : [],
    fetchedAt: new Date().toISOString(),
  };
}
