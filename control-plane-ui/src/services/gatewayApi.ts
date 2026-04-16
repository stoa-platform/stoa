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
  apis: GatewayAPIResponse[] | null;
  applications: GatewayApplicationResponse[] | null;
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

/**
 * Fetch full gateway status (health + APIs + applications).
 *
 * Contract (CAB-1887 G2): this function surfaces errors instead of silently
 * returning empty data. If ALL three endpoints fail, it throws so callers
 * (React Query) can render an explicit error state with a retry button.
 * If at least one endpoint succeeds, the response is returned and failed
 * slices are marked via `health.error` / `apis === null` / `applications === null`.
 */
export async function getGatewayStatus(): Promise<GatewayStatusResponse> {
  const fallbackHealth: GatewayHealthResponse = { status: 'unhealthy', proxy_mode: false };

  const [healthResult, apisResult, appsResult] = await Promise.allSettled([
    getGatewayHealth(),
    getGatewayAPIs(),
    getGatewayApplications(),
  ]);

  const allFailed =
    healthResult.status === 'rejected' &&
    apisResult.status === 'rejected' &&
    appsResult.status === 'rejected';

  if (allFailed) {
    const reason = (healthResult as PromiseRejectedResult).reason;
    throw new Error(
      `Failed to load gateway status: ${reason instanceof Error ? reason.message : String(reason)}`
    );
  }

  return {
    health:
      healthResult.status === 'fulfilled'
        ? healthResult.value
        : { ...fallbackHealth, error: String((healthResult as PromiseRejectedResult).reason) },
    apis: apisResult.status === 'fulfilled' ? apisResult.value : null,
    applications: appsResult.status === 'fulfilled' ? appsResult.value : null,
    fetchedAt: new Date().toISOString(),
  };
}
