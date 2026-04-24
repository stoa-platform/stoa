import { httpClient, path } from '../http';

// ── Chat Settings (CAB-1852) ─────────────────────────────────────────────────

export interface TenantChatSettings {
  chat_console_enabled: boolean;
  chat_portal_enabled: boolean;
  chat_daily_budget: number;
}

// ── Chat usage by source — per-app breakdown (CAB-1868) ─────────────────────

export interface ChatSourceEntry {
  source: string;
  tokens: number;
  requests: number;
}

export interface ChatUsageBySource {
  sources: ChatSourceEntry[];
  total_tokens: number;
  total_requests: number;
  period_days: number;
}

// ── Chat token metering (CAB-288) ───────────────────────────────────────────

export interface TokenBudgetStatus {
  user_tokens_today: number;
  tenant_tokens_today: number;
  daily_budget: number;
  remaining: number;
  budget_exceeded: boolean;
  usage_percent: number;
}

export interface TokenUsageStats {
  tenant_id: string;
  period_days: number;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_requests: number;
  today_tokens: number;
  top_users: { user_id: string; tokens: number }[];
  daily_breakdown: { date: string; tokens: number }[];
}

// ── Chat conversation metrics (CAB-1868) ────────────────────────────────────

export interface ChatConversationMetrics {
  tenant_id: string;
  total_conversations: number;
  total_messages: number;
  total_tokens: number;
  unique_users: number;
}

export interface ModelDistributionEntry {
  model: string;
  conversations: number;
}

export interface ChatModelDistribution {
  models: ModelDistributionEntry[];
  total_conversations: number;
}

export const chatClient = {
  async getSettings(tenantId: string): Promise<TenantChatSettings> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'chat', 'settings'));
    return data;
  },

  async updateSettings(
    tenantId: string,
    settings: Partial<TenantChatSettings>
  ): Promise<TenantChatSettings> {
    const { data } = await httpClient.put(
      path('v1', 'tenants', tenantId, 'chat', 'settings'),
      settings
    );
    return data;
  },

  async getBudgetStatus(tenantId: string): Promise<TokenBudgetStatus> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'chat', 'usage', 'budget')
    );
    return data;
  },

  async getUsageStats(tenantId: string, days = 30): Promise<TokenUsageStats> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'chat', 'usage', 'metering'),
      {
        params: { days },
      }
    );
    return data;
  },

  async getUsageBySource(
    tenantId: string,
    params: { group_by?: string; days?: number } = {}
  ): Promise<ChatUsageBySource> {
    // P1-13: spread in last position with a null-coalescing default so
    // callers passing `{ group_by: undefined, days: 7 }` do NOT override
    // the default with undefined (which axios then drops, forcing the
    // backend fallback instead of the client's intended default).
    const safeParams = params ?? {};
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'chat', 'usage', 'tenant'),
      {
        params: { ...safeParams, group_by: safeParams.group_by ?? 'source' },
      }
    );
    return data;
  },

  async getConversationMetrics(tenantId: string): Promise<ChatConversationMetrics> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'chat', 'usage', 'tenant')
    );
    return data;
  },

  async getModelDistribution(tenantId: string): Promise<ChatModelDistribution> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'chat', 'usage', 'models')
    );
    return data;
  },

  async createConversation(tenantId: string, title = 'New conversation'): Promise<{ id: string }> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'chat', 'conversations'),
      {
        title,
      }
    );
    return data;
  },
};
