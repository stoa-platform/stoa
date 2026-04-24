import type { Schemas } from '@stoa/shared/api-types';
import { httpClient, path } from '../http';

// ── Monitoring / Call flow (CAB-1869) ────────────────────────────────────────

// Detail view: canonicalized on the backend schema. The list endpoint shape
// is not yet extracted as a dedicated backend schema — `MonitoringTransaction`
// stays a local summary until backend exposes `TransactionListItem`.
// DRIFT: monitoring transaction list response is not yet a dedicated
// backend schema. Keep this summary shape local.
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

export type MonitoringTransactionDetail = Schemas['TransactionDetailWithDemoResponse'];

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
    // P1-14: `!= null` keeps `0` (valid for numeric params) and blocks a
    // caller that explicitly passed `null`. `if (x)` would drop `0` and
    // `''` alike — not what we want for numeric-or-string params.
    const params: Record<string, string | number> = { limit };
    if (status != null) params.status = status;
    if (timeRange != null) params.time_range = timeRange;
    if (serviceType != null) params.service_type = serviceType;
    if (statusCode != null) params.status_code = statusCode;
    if (route != null) params.route = route;
    const { data } = await httpClient.get('/v1/monitoring/transactions', { params });
    return data;
  },

  async getTransactionDetail(transactionId: string): Promise<MonitoringTransactionDetail> {
    const { data } = await httpClient.get(path('v1', 'monitoring', 'transactions', transactionId));
    return data;
  },

  async getTransactionStats(timeRange?: string): Promise<MonitoringStats> {
    const params: Record<string, string> = {};
    if (timeRange != null) params.time_range = timeRange;
    const { data } = await httpClient.get('/v1/monitoring/transactions/stats', { params });
    return data;
  },
};
