import { httpClient, path } from '../http';
import type { PipelineTrace, TraceStats, TraceSummary, TraceTimeline } from '../../types';

export const tracesClient = {
  async list(
    limit?: number,
    tenantId?: string,
    status?: string,
    environment?: string
  ): Promise<{ traces: TraceSummary[]; total: number }> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const params: Record<string, any> = {};
    // P1-14: use != null to keep legitimate 0 / empty-string values
    if (limit != null) params.limit = limit;
    if (tenantId != null) params.tenant_id = tenantId;
    if (status != null) params.status = status;
    if (environment != null) params.environment = environment;
    const { data } = await httpClient.get('/v1/traces', { params });
    return data;
  },

  async get(traceId: string): Promise<PipelineTrace> {
    const { data } = await httpClient.get(path('v1', 'traces', traceId));
    return data;
  },

  async getTimeline(traceId: string): Promise<TraceTimeline> {
    const { data } = await httpClient.get(path('v1', 'traces', traceId, 'timeline'));
    return data;
  },

  async getStats(): Promise<TraceStats> {
    const { data } = await httpClient.get('/v1/traces/stats');
    return data;
  },

  async listLive(): Promise<{ traces: PipelineTrace[]; count: number }> {
    const { data } = await httpClient.get('/v1/traces/live');
    return data;
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getAiSessionStats(days?: number, worker?: string): Promise<any> {
    const params: Record<string, string | number> = {};
    if (days != null) params.days = days;
    if (worker != null) params.worker = worker;
    const { data } = await httpClient.get('/v1/traces/stats/ai-sessions', { params });
    return data;
  },

  async exportAiSessionsCsv(days?: number, worker?: string): Promise<Blob> {
    const params: Record<string, string | number> = {};
    if (days != null) params.days = days;
    if (worker != null) params.worker = worker;
    const { data } = await httpClient.get('/v1/traces/export/ai-sessions', {
      params,
      responseType: 'blob',
    });
    return data;
  },
};
