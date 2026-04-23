import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockHttpClient } = vi.hoisted(() => ({
  mockHttpClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../services/http', () => ({
  httpClient: mockHttpClient,
}));

import { platformClient } from '../../../services/api/platform';
import { chatClient } from '../../../services/api/chat';
import { llmClient } from '../../../services/api/llm';
import { monitoringClient } from '../../../services/api/monitoring';

describe('UI-2 S3 domain clients', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('covers platformClient request delegation', async () => {
    const status = { timestamp: '2026-04-22T00:00:00Z' };
    const components = [{ name: 'api' }];
    const component = { name: 'api', health_status: 'healthy' };
    const sync = { message: 'started', operation: 'sync' };
    const diff = { application: 'api', total_resources: 1, diff_count: 0, resources: [] };
    const events = [{ id: 1, component: 'api' }];
    const operations = { error_rate: 0.1 };
    const business = { active_tenants: 2 };
    const topApis = [{ tool_name: 'payments', display_name: 'Payments', calls: 42 }];

    mockHttpClient.get
      .mockResolvedValueOnce({ data: status })
      .mockResolvedValueOnce({ data: components })
      .mockResolvedValueOnce({ data: component })
      .mockResolvedValueOnce({ data: diff })
      .mockResolvedValueOnce({ data: events })
      .mockResolvedValueOnce({ data: operations })
      .mockResolvedValueOnce({ data: business })
      .mockResolvedValueOnce({ data: topApis });
    mockHttpClient.post.mockResolvedValueOnce({ data: sync });

    await expect(platformClient.getStatus()).resolves.toBe(status as never);
    await expect(platformClient.listComponents()).resolves.toBe(components as never);
    await expect(platformClient.getComponent('api')).resolves.toBe(component as never);
    await expect(platformClient.syncComponent('api')).resolves.toBe(sync);
    await expect(platformClient.getComponentDiff('api')).resolves.toBe(diff as never);
    await expect(platformClient.listEvents('api', 15)).resolves.toBe(events as never);
    await expect(platformClient.getOperationsMetrics()).resolves.toBe(operations as never);
    await expect(platformClient.getBusinessMetrics()).resolves.toBe(business as never);
    await expect(platformClient.getTopAPIs(5)).resolves.toBe(topApis as never);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/platform/status');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/platform/components');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(3, '/v1/platform/components/api');
    expect(mockHttpClient.post).toHaveBeenCalledWith('/v1/platform/components/api/sync');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(4, '/v1/platform/components/api/diff');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(5, '/v1/platform/events', {
      params: { component: 'api', limit: 15 },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(6, '/v1/operations/metrics');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(7, '/v1/business/metrics');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(8, '/v1/business/top-apis?limit=5');
  });

  it('covers chatClient request delegation', async () => {
    const settings = {
      chat_console_enabled: true,
      chat_portal_enabled: false,
      chat_daily_budget: 1000,
    };
    const budget = {
      user_tokens_today: 10,
      tenant_tokens_today: 100,
      daily_budget: 1000,
      remaining: 900,
      budget_exceeded: false,
      usage_percent: 10,
    };
    const usage = {
      tenant_id: 'tenant-1',
      period_days: 7,
      total_tokens: 1000,
      total_input_tokens: 600,
      total_output_tokens: 400,
      total_requests: 10,
      today_tokens: 100,
      top_users: [],
      daily_breakdown: [],
    };
    const bySource = {
      sources: [{ source: 'console', tokens: 100, requests: 2 }],
      total_tokens: 100,
      total_requests: 2,
      period_days: 7,
    };
    const conversationMetrics = {
      tenant_id: 'tenant-1',
      total_conversations: 5,
      total_messages: 20,
      total_tokens: 1000,
      unique_users: 3,
    };
    const models = {
      models: [{ model: 'gpt-5.4', conversations: 5 }],
      total_conversations: 5,
    };
    const conversation = { id: 'conv-1' };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: settings })
      .mockResolvedValueOnce({ data: budget })
      .mockResolvedValueOnce({ data: usage })
      .mockResolvedValueOnce({ data: bySource })
      .mockResolvedValueOnce({ data: conversationMetrics })
      .mockResolvedValueOnce({ data: models });
    mockHttpClient.put.mockResolvedValueOnce({ data: settings });
    mockHttpClient.post.mockResolvedValueOnce({ data: conversation });

    await expect(chatClient.getSettings('tenant-1')).resolves.toBe(settings);
    await expect(
      chatClient.updateSettings('tenant-1', {
        chat_portal_enabled: true,
      })
    ).resolves.toBe(settings);
    await expect(chatClient.getBudgetStatus('tenant-1')).resolves.toBe(budget);
    await expect(chatClient.getUsageStats('tenant-1', 7)).resolves.toBe(usage);
    await expect(
      chatClient.getUsageBySource('tenant-1', { days: 7, group_by: 'source' })
    ).resolves.toBe(bySource);
    await expect(chatClient.getConversationMetrics('tenant-1')).resolves.toBe(conversationMetrics);
    await expect(chatClient.getModelDistribution('tenant-1')).resolves.toBe(models);
    await expect(chatClient.createConversation('tenant-1', 'Runbook')).resolves.toBe(conversation);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/chat/settings');
    expect(mockHttpClient.put).toHaveBeenCalledWith('/v1/tenants/tenant-1/chat/settings', {
      chat_portal_enabled: true,
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/tenants/tenant-1/chat/usage/budget');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/chat/usage/metering',
      {
        params: { days: 7 },
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/chat/usage/tenant',
      {
        params: { group_by: 'source', days: 7 },
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(5, '/v1/tenants/tenant-1/chat/usage/tenant');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(6, '/v1/tenants/tenant-1/chat/usage/models');
    expect(mockHttpClient.post).toHaveBeenCalledWith('/v1/tenants/tenant-1/chat/conversations', {
      title: 'Runbook',
    });
  });

  it('covers llmClient request delegation', async () => {
    const usage = {
      total_cost_usd: 10,
      input_tokens: 1000,
      output_tokens: 500,
      avg_cost_per_request: 1,
      cache_read_cost_usd: 0,
      cache_write_cost_usd: 0,
      period: 'month',
    };
    const timeseries = {
      points: [{ timestamp: '2026-04-22T00:00:00Z', value: 12 }],
      period: 'week',
      step: 'day',
    };
    const providers = {
      providers: [{ provider: 'openai', model: 'gpt-5.4', cost_usd: 10 }],
      period: 'month',
    };
    const budget = {
      id: 'budget-1',
      tenant_id: 'tenant-1',
      monthly_limit_usd: 100,
      current_spend_usd: 20,
      remaining_usd: 80,
      usage_pct: 20,
      alert_threshold_pct: 80,
      is_over_budget: false,
    };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: usage })
      .mockResolvedValueOnce({ data: timeseries })
      .mockResolvedValueOnce({ data: providers })
      .mockResolvedValueOnce({ data: budget });
    mockHttpClient.put.mockResolvedValueOnce({ data: budget });

    await expect(llmClient.getUsage('tenant-1', 'month')).resolves.toBe(usage);
    await expect(llmClient.getTimeseries('tenant-1', 'week')).resolves.toBe(timeseries);
    await expect(llmClient.getProviderBreakdown('tenant-1', 'month')).resolves.toBe(providers);
    await expect(llmClient.getBudget('tenant-1')).resolves.toBe(budget);
    await expect(
      llmClient.updateBudget('tenant-1', {
        monthly_limit_usd: 120,
        alert_threshold_pct: 85,
      })
    ).resolves.toBe(budget);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/llm/usage', {
      params: { period: 'month' },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/llm/usage/timeseries',
      {
        params: { period: 'week' },
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/llm/usage/providers',
      {
        params: { period: 'month' },
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(4, '/v1/tenants/tenant-1/llm/budget');
    expect(mockHttpClient.put).toHaveBeenCalledWith('/v1/tenants/tenant-1/llm/budget', {
      monthly_limit_usd: 120,
      alert_threshold_pct: 85,
    });
  });

  it('covers monitoringClient request delegation', async () => {
    const transactions = { transactions: [{ id: 'txn-1' }] };
    const transaction = { id: 'txn-1', trace_id: 'trace-1', spans: [] };
    const stats = {
      total_requests: 10,
      success_count: 9,
      error_count: 1,
      timeout_count: 0,
      avg_latency_ms: 100,
      p95_latency_ms: 180,
      requests_per_minute: 2,
      by_api: { payments: 10 },
      by_status_code: { '200': 9, '500': 1 },
    };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: transactions })
      .mockResolvedValueOnce({ data: transaction })
      .mockResolvedValueOnce({ data: stats });

    await expect(
      monitoringClient.listTransactions(30, 'error', '24h', 'gateway', 500, '/payments')
    ).resolves.toBe(transactions);
    await expect(monitoringClient.getTransactionDetail('txn-1')).resolves.toBe(
      transaction as never
    );
    await expect(monitoringClient.getTransactionStats('24h')).resolves.toBe(stats);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/monitoring/transactions', {
      params: {
        limit: 30,
        status: 'error',
        time_range: '24h',
        service_type: 'gateway',
        status_code: 500,
        route: '/payments',
      },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/monitoring/transactions/txn-1');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(3, '/v1/monitoring/transactions/stats', {
      params: { time_range: '24h' },
    });
  });
});
