import { httpClient, path } from '../http';

// ── Platform Status (CAB-654) ────────────────────────────────────────────────

export interface ComponentStatus {
  name: string;
  display_name: string;
  sync_status: string;
  health_status: string;
  revision: string;
  last_sync: string | null;
  message: string | null;
}

export interface GitOpsStatus {
  status: string;
  components: ComponentStatus[];
  checked_at: string;
}

export interface PlatformEvent {
  id: number | null;
  component: string;
  event_type: string;
  status: string;
  revision: string;
  message: string | null;
  timestamp: string;
  actor: string | null;
}

export interface ExternalLinks {
  argocd: string;
  grafana: string;
  prometheus: string;
  logs: string;
}

export interface PlatformStatusResponse {
  gitops: GitOpsStatus;
  events: PlatformEvent[];
  external_links: ExternalLinks;
  timestamp: string;
}

export interface ApplicationDiffResource {
  name: string;
  namespace: string | null;
  kind: string;
  group: string | null;
  status: string;
  health: string | null;
  diff: string | null;
}

export interface ApplicationDiffResponse {
  application: string;
  total_resources: number;
  diff_count: number;
  resources: ApplicationDiffResource[];
}

// ── Operations metrics (CAB-Observability) ──────────────────────────────────

export interface OperationsMetrics {
  error_rate: number;
  p95_latency_ms: number;
  requests_per_minute: number;
  active_alerts: number;
  uptime: number;
}

// ── Business analytics (CAB-Observability) ──────────────────────────────────

export interface BusinessMetrics {
  active_tenants: number;
  new_tenants_30d: number;
  tenant_growth: number;
  apdex_score: number;
  total_tokens: number;
  total_calls: number;
}

export interface TopAPI {
  tool_name: string;
  display_name: string;
  calls: number;
}

export const platformClient = {
  // Status
  async getStatus(): Promise<PlatformStatusResponse> {
    const { data } = await httpClient.get('/v1/platform/status');
    return data;
  },

  async listComponents(): Promise<ComponentStatus[]> {
    const { data } = await httpClient.get('/v1/platform/components');
    return data;
  },

  async getComponent(name: string): Promise<ComponentStatus> {
    const { data } = await httpClient.get(path('v1', 'platform', 'components', name));
    return data;
  },

  async syncComponent(name: string): Promise<{ message: string; operation: string }> {
    const { data } = await httpClient.post(path('v1', 'platform', 'components', name, 'sync'));
    return data;
  },

  async getComponentDiff(name: string): Promise<ApplicationDiffResponse> {
    const { data } = await httpClient.get(path('v1', 'platform', 'components', name, 'diff'));
    return data;
  },

  async listEvents(component?: string, limit?: number): Promise<PlatformEvent[]> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const params: Record<string, any> = {};
    // P1-14: != null preserves 0 (valid limit value) and blocks explicit null
    if (component != null) params.component = component;
    if (limit != null) params.limit = limit;
    const { data } = await httpClient.get('/v1/platform/events', { params });
    return data;
  },

  // Operations
  async getOperationsMetrics(): Promise<OperationsMetrics> {
    const { data } = await httpClient.get('/v1/operations/metrics');
    return data;
  },

  // Business
  async getBusinessMetrics(): Promise<BusinessMetrics> {
    const { data } = await httpClient.get('/v1/business/metrics');
    return data;
  },

  async getTopAPIs(limit = 10): Promise<TopAPI[]> {
    // P1-11 residu: use axios params option rather than inline template string.
    const { data } = await httpClient.get('/v1/business/top-apis', {
      params: { limit },
    });
    return data;
  },
};
