import { httpClient } from '../http';

// ── Monitoring / Call flow (CAB-1869) ────────────────────────────────────────

export interface MonitoringTransaction {
  id: string;
  trace_id: string;
  api_name: string;
  method: string;
  path: string;
  status_code: number;
  status: string;
  status_text: string;
  error_source: string | null;
  started_at: string;
  total_duration_ms: number;
  spans_count: number;
  deployment_mode?: string;
  spans?: Array<{
    name: string;
    service: string;
    start_offset_ms: number;
    duration_ms: number;
    status: string;
  }>;
}

export interface MonitoringTransactionDetail extends MonitoringTransaction {
  tenant_id: string | null;
  client_ip: string | null;
  user_id: string | null;
  spans: Array<{
    name: string;
    service: string;
    start_offset_ms: number;
    duration_ms: number;
    status: string;
    metadata: Record<string, unknown>;
  }>;
  request_headers: Record<string, string> | null;
  response_headers: Record<string, string> | null;
  error_message: string | null;
  demo_mode: boolean;
}

export interface MonitoringStats {
  total_requests: number;
  success_count: number;
  error_count: number;
  timeout_count: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  requests_per_minute: number;
  by_api: Record<string, number>;
  by_status_code: Record<string, number>;
}

export const monitoringClient = {
  async listTransactions(
    limit = 20,
    status?: string,
    timeRange?: string,
    serviceType?: string,
    statusCode?: number,
    route?: string
  ): Promise<{ transactions: MonitoringTransaction[] }> {
    const params: Record<string, string | number> = { limit };
    if (status) params.status = status;
    if (timeRange) params.time_range = timeRange;
    if (serviceType) params.service_type = serviceType;
    if (statusCode) params.status_code = statusCode;
    if (route) params.route = route;
    const { data } = await httpClient.get('/v1/monitoring/transactions', { params });
    return data;
  },

  async getTransactionDetail(transactionId: string): Promise<MonitoringTransactionDetail> {
    const { data } = await httpClient.get(`/v1/monitoring/transactions/${transactionId}`);
    return data;
  },

  async getTransactionStats(timeRange?: string): Promise<MonitoringStats> {
    const params: Record<string, string> = {};
    if (timeRange) params.time_range = timeRange;
    const { data } = await httpClient.get('/v1/monitoring/transactions/stats', { params });
    return data;
  },
};
