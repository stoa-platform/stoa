import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LLMCostDashboard } from './LLMCostDashboard';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockProviders = [
  {
    id: 'prov-1',
    tenant_id: 'oasis-gunters',
    provider_name: 'anthropic',
    display_name: 'Anthropic Claude',
    default_model: 'claude-sonnet-4-6',
    cost_per_input_token: 0.003,
    cost_per_output_token: 0.015,
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
  {
    id: 'prov-2',
    tenant_id: 'oasis-gunters',
    provider_name: 'openai',
    display_name: 'OpenAI GPT',
    default_model: 'gpt-4o',
    cost_per_input_token: 0.005,
    cost_per_output_token: 0.015,
    status: 'rate_limited',
    created_at: '2026-01-15T00:00:00Z',
    updated_at: '2026-02-15T00:00:00Z',
  },
  {
    id: 'prov-3',
    tenant_id: 'oasis-gunters',
    provider_name: 'mistral',
    display_name: null,
    default_model: null,
    cost_per_input_token: 0.001,
    cost_per_output_token: 0.003,
    status: 'inactive',
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
];

const mockBudget = {
  id: 'budget-1',
  tenant_id: 'oasis-gunters',
  monthly_limit_usd: 1000,
  current_spend_usd: 450.75,
  alert_threshold_pct: 80,
  usage_pct: 45.075,
  remaining_usd: 549.25,
  is_over_budget: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-25T00:00:00Z',
};

const mockGet = vi.fn();
const mockGetLlmUsage = vi.fn();
const mockGetLlmTimeseries = vi.fn();
const mockGetLlmProviderBreakdown = vi.fn();

vi.mock('../../services/api', () => ({
  apiService: {
    get: (...args: unknown[]) => mockGet(...args),
    getLlmUsage: (...args: unknown[]) => mockGetLlmUsage(...args),
    getLlmTimeseries: (...args: unknown[]) => mockGetLlmTimeseries(...args),
    getLlmProviderBreakdown: (...args: unknown[]) => mockGetLlmProviderBreakdown(...args),
  },
}));

const mockUsage = {
  total_cost_usd: 12.345,
  input_tokens: 50000,
  output_tokens: 20000,
  avg_cost_per_request: 0.001234,
  cache_read_cost_usd: 0.5,
  cache_write_cost_usd: 0.1,
  period: 'month',
};

const mockTimeseries = {
  points: [
    { timestamp: '2026-02-28T00:00:00Z', value: 1.5 },
    { timestamp: '2026-02-28T01:00:00Z', value: 2.3 },
  ],
  period: 'day',
  step: '1h',
};

const mockProviderCosts = {
  providers: [
    { provider: 'anthropic', model: 'claude-3-5-sonnet', cost_usd: 8.5 },
    { provider: 'openai', model: 'gpt-4o', cost_usd: 3.2 },
  ],
  period: 'month',
};

function setupApiMock(providers = mockProviders, budget: typeof mockBudget | null = mockBudget) {
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/providers')) {
      return Promise.resolve({ data: providers });
    }
    if (url.includes('/budget')) {
      if (budget === null) {
        return Promise.reject(new Error('Budget not found'));
      }
      return Promise.resolve({ data: budget });
    }
    return Promise.resolve({ data: {} });
  });
  mockGetLlmUsage.mockResolvedValue(mockUsage);
  mockGetLlmTimeseries.mockResolvedValue(mockTimeseries);
  mockGetLlmProviderBreakdown.mockResolvedValue(mockProviderCosts);
}

describe('LLMCostDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    setupApiMock();
  });

  it('renders the page title', async () => {
    renderWithProviders(<LLMCostDashboard />);
    await waitFor(() => {
      expect(screen.getByText('LLM Cost Management')).toBeInTheDocument();
    });
  });

  it('renders the subtitle with tenant ID', async () => {
    renderWithProviders(<LLMCostDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/Monitor LLM spend and manage provider budgets/)).toBeInTheDocument();
    });
  });

  it('renders refresh button', async () => {
    renderWithProviders(<LLMCostDashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('refresh-btn')).toBeInTheDocument();
    });
  });

  it('shows loading skeletons initially', () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<LLMCostDashboard />);
    expect(screen.queryByTestId('budget-cards')).not.toBeInTheDocument();
  });

  describe('Budget Overview Cards', () => {
    it('shows budget cards after loading', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('budget-cards')).toBeInTheDocument();
      });
    });

    it('shows monthly budget value', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Monthly Budget')).toBeInTheDocument();
        expect(screen.getAllByText('$1000').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows current spend value', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Current Spend')).toBeInTheDocument();
        expect(screen.getByText('$450.75')).toBeInTheDocument();
      });
    });

    it('shows active providers count', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Active Providers')).toBeInTheDocument();
      });
    });

    it('shows budget usage percentage', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Budget Usage')).toBeInTheDocument();
        expect(screen.getByText('45%')).toBeInTheDocument();
      });
    });

    it('shows N/A for budget when no budget set', async () => {
      setupApiMock(mockProviders, null);
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('N/A')).toBeInTheDocument();
      });
    });
  });

  describe('Budget Progress Bar', () => {
    it('renders budget progress bar', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('budget-progress')).toBeInTheDocument();
      });
    });

    it('shows utilization text', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Budget Utilization')).toBeInTheDocument();
      });
    });

    it('shows alert threshold', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Alert at 80%')).toBeInTheDocument();
      });
    });

    it('renders progress bar with correct width', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        const bar = screen.getByTestId('budget-bar');
        expect(bar).toHaveStyle({ width: '45.075%' });
      });
    });

    it('does not render progress bar when no budget', async () => {
      setupApiMock(mockProviders, null);
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('LLM Cost Management')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('budget-progress')).not.toBeInTheDocument();
    });
  });

  describe('Over Budget Alert', () => {
    it('shows alert when over budget', async () => {
      setupApiMock(mockProviders, {
        ...mockBudget,
        is_over_budget: true,
        remaining_usd: -50.25,
        usage_pct: 105,
      });
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('over-budget-alert')).toBeInTheDocument();
        expect(screen.getByText(/Over Budget/)).toBeInTheDocument();
      });
    });

    it('hides alert when under budget', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('LLM Cost Management')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('over-budget-alert')).not.toBeInTheDocument();
    });
  });

  describe('Providers Table', () => {
    it('renders provider names', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Anthropic Claude')).toBeInTheDocument();
        expect(screen.getByText('OpenAI GPT')).toBeInTheDocument();
        expect(screen.getByText('mistral')).toBeInTheDocument();
      });
    });

    it('renders provider slug under display name', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getAllByText('anthropic').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('openai').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders default models', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getAllByText('claude-sonnet-4-6').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('gpt-4o').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows dash for providers without model', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        const dashes = screen.getAllByText('—');
        expect(dashes.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders status badges', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('provider-status-active')).toBeInTheDocument();
        expect(screen.getByTestId('provider-status-rate_limited')).toBeInTheDocument();
        expect(screen.getByTestId('provider-status-inactive')).toBeInTheDocument();
      });
    });

    it('shows rate limited badge in header', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('rate-limited-badge')).toBeInTheDocument();
        expect(screen.getByText('1 rate limited')).toBeInTheDocument();
      });
    });

    it('hides rate limited badge when none rate limited', async () => {
      setupApiMock([mockProviders[0]]);
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Anthropic Claude')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('rate-limited-badge')).not.toBeInTheDocument();
    });

    it('shows empty state when no providers', async () => {
      setupApiMock([]);
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(
          screen.getByText('No LLM providers configured for this tenant.')
        ).toBeInTheDocument();
      });
    });

    it('renders cost per token values', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getAllByText('$0.0030/tok').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('$0.0150/tok').length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  describe('Period Selector', () => {
    it('renders period selector buttons', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('period-selector')).toBeInTheDocument();
      });
      expect(screen.getByTestId('period-hour')).toBeInTheDocument();
      expect(screen.getByTestId('period-day')).toBeInTheDocument();
      expect(screen.getByTestId('period-week')).toBeInTheDocument();
      expect(screen.getByTestId('period-month')).toBeInTheDocument();
    });

    it('defaults to month period', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('period-month')).toHaveClass('bg-blue-600');
      });
    });

    it('changes period on click and refetches', async () => {
      const user = userEvent.setup();
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('period-selector')).toBeInTheDocument();
      });
      await user.click(screen.getByTestId('period-day'));
      await waitFor(() => {
        expect(mockGetLlmUsage).toHaveBeenCalledWith(expect.anything(), 'day');
      });
    });
  });

  describe('Usage KPI Cards (Prometheus)', () => {
    it('shows usage cards when data available', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('usage-cards')).toBeInTheDocument();
      });
    });

    it('displays total cost', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Total Cost')).toBeInTheDocument();
        expect(screen.getByText('$12.3450')).toBeInTheDocument();
      });
    });

    it('displays tokens used', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Tokens Used')).toBeInTheDocument();
        expect(screen.getByText('70.0K')).toBeInTheDocument();
      });
    });

    it('displays average cost per request', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Avg Cost / Request')).toBeInTheDocument();
        expect(screen.getByText('$0.001234')).toBeInTheDocument();
      });
    });

    it('displays cache savings', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Cache Savings')).toBeInTheDocument();
        expect(screen.getByText('$0.6000')).toBeInTheDocument();
      });
    });

    it('hides usage cards when Prometheus unavailable', async () => {
      mockGetLlmUsage.mockRejectedValue(new Error('503'));
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('budget-cards')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('usage-cards')).not.toBeInTheDocument();
    });
  });

  describe('Cost Time-Series Chart', () => {
    it('renders timeseries chart', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('cost-timeseries')).toBeInTheDocument();
      });
    });

    it('renders bars for each data point', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        const bars = screen.getByTestId('timeseries-bars');
        expect(bars.children).toHaveLength(2);
      });
    });

    it('shows step label', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Step: 1h')).toBeInTheDocument();
      });
    });

    it('hides chart when no timeseries data', async () => {
      mockGetLlmTimeseries.mockResolvedValue({ points: [], period: 'day', step: '1h' });
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('budget-cards')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('cost-timeseries')).not.toBeInTheDocument();
    });
  });

  describe('Provider Cost Breakdown (Prometheus)', () => {
    it('renders provider cost breakdown table', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('provider-cost-breakdown')).toBeInTheDocument();
      });
    });

    it('shows provider cost rows', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('cost-row-anthropic-claude-3-5-sonnet')).toBeInTheDocument();
        expect(screen.getByTestId('cost-row-openai-gpt-4o')).toBeInTheDocument();
      });
    });

    it('displays cost amounts', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('$8.5000')).toBeInTheDocument();
        expect(screen.getByText('$3.2000')).toBeInTheDocument();
      });
    });

    it('displays share percentages', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('72.6%')).toBeInTheDocument();
        expect(screen.getByText('27.4%')).toBeInTheDocument();
      });
    });

    it('hides breakdown when no cost data', async () => {
      mockGetLlmProviderBreakdown.mockResolvedValue({ providers: [], period: 'month' });
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('budget-cards')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('provider-cost-breakdown')).not.toBeInTheDocument();
    });
  });

  describe('Refresh', () => {
    it('calls API on refresh click', async () => {
      const user = userEvent.setup();
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Anthropic Claude')).toBeInTheDocument();
      });
      const refreshBtn = screen.getByTestId('refresh-btn');
      await user.click(refreshBtn);
      // Each refresh calls 5 endpoints (providers + budget + usage + timeseries + breakdown)
      expect(mockGet).toHaveBeenCalledTimes(4);
      expect(mockGetLlmUsage).toHaveBeenCalledTimes(2);
    });
  });

  describe('RBAC-gated Actions', () => {
    it('shows Actions column for cpi-admin', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Actions')).toBeInTheDocument();
      });
    });

    it('shows Actions column for tenant-admin', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Actions')).toBeInTheDocument();
      });
    });

    it('hides Actions column for devops', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('devops'));
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Anthropic Claude')).toBeInTheDocument();
      });
      expect(screen.queryByText('Actions')).not.toBeInTheDocument();
    });

    it('hides Actions column for viewer', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Anthropic Claude')).toBeInTheDocument();
      });
      expect(screen.queryByText('Actions')).not.toBeInTheDocument();
    });

    it('shows Delete buttons for providers', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('delete-provider-prov-1')).toBeInTheDocument();
        expect(screen.getByTestId('delete-provider-prov-2')).toBeInTheDocument();
      });
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      });

      it('renders the page', async () => {
        renderWithProviders(<LLMCostDashboard />);
        await waitFor(() => {
          expect(screen.getByText('LLM Cost Management')).toBeInTheDocument();
        });
      });

      it('shows budget cards', async () => {
        renderWithProviders(<LLMCostDashboard />);
        await waitFor(() => {
          expect(screen.getByTestId('budget-cards')).toBeInTheDocument();
        });
      });

      it('shows providers table', async () => {
        renderWithProviders(<LLMCostDashboard />);
        await waitFor(() => {
          expect(screen.getByTestId('providers-table-body')).toBeInTheDocument();
        });
      });

      it('shows provider names', async () => {
        renderWithProviders(<LLMCostDashboard />);
        await waitFor(() => {
          expect(screen.getByText('Anthropic Claude')).toBeInTheDocument();
        });
      });
    }
  );
});
