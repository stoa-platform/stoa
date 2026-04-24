import { httpClient, path } from '../http';

// ── LLM usage & cost (CAB-1487) ──────────────────────────────────────────────

export interface LlmUsageResponse {
  total_cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  avg_cost_per_request: number;
  cache_read_cost_usd: number;
  cache_write_cost_usd: number;
  period: string;
}

export interface LlmTimeseriesPoint {
  timestamp: string;
  value: number;
}

export interface LlmTimeseriesResponse {
  points: LlmTimeseriesPoint[];
  period: string;
  step: string;
}

export interface LlmProviderCostEntry {
  provider: string;
  model: string;
  cost_usd: number;
}

export interface LlmProviderBreakdownResponse {
  providers: LlmProviderCostEntry[];
  period: string;
}

export interface LlmBudgetResponse {
  id: string;
  tenant_id: string;
  monthly_limit_usd: number;
  current_spend_usd: number;
  remaining_usd: number;
  usage_pct: number;
  alert_threshold_pct: number;
  is_over_budget: boolean;
}

type LlmPeriod = 'hour' | 'day' | 'week' | 'month';

export const llmClient = {
  async getUsage(tenantId: string, period: LlmPeriod = 'month'): Promise<LlmUsageResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'llm', 'usage'), {
      params: { period },
    });
    return data;
  },

  async getTimeseries(
    tenantId: string,
    period: LlmPeriod = 'week'
  ): Promise<LlmTimeseriesResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'llm', 'usage', 'timeseries'), {
      params: { period },
    });
    return data;
  },

  async getProviderBreakdown(
    tenantId: string,
    period: LlmPeriod = 'month'
  ): Promise<LlmProviderBreakdownResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'llm', 'usage', 'providers'), {
      params: { period },
    });
    return data;
  },

  async getBudget(tenantId: string): Promise<LlmBudgetResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'llm', 'budget'));
    return data;
  },

  async updateBudget(
    tenantId: string,
    update: { monthly_limit_usd?: number; alert_threshold_pct?: number }
  ): Promise<LlmBudgetResponse> {
    const { data } = await httpClient.put(path('v1', 'tenants', tenantId, 'llm', 'budget'), update);
    return data;
  },
};
