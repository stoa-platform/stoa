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

vi.mock('../../services/api', () => ({
  apiService: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

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
        expect(screen.getByText('anthropic')).toBeInTheDocument();
        expect(screen.getByText('openai')).toBeInTheDocument();
      });
    });

    it('renders default models', async () => {
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('claude-sonnet-4-6')).toBeInTheDocument();
        expect(screen.getByText('gpt-4o')).toBeInTheDocument();
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

  describe('Refresh', () => {
    it('calls API on refresh click', async () => {
      const user = userEvent.setup();
      renderWithProviders(<LLMCostDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Anthropic Claude')).toBeInTheDocument();
      });
      const refreshBtn = screen.getByTestId('refresh-btn');
      await user.click(refreshBtn);
      // Each refresh calls 2 endpoints (providers + budget)
      expect(mockGet).toHaveBeenCalledTimes(4);
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
