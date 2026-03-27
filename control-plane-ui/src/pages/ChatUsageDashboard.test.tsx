import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatUsageDashboard } from './ChatUsageDashboard';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
vi.mock('../services/api', () => ({
  apiService: {
    getChatUsageTenant: vi.fn(),
    getChatBudgetStatus: vi.fn(),
    getChatConversationMetrics: vi.fn(),
    getChatModelDistribution: vi.fn(),
  },
}));

// Recharts ResponsiveContainer needs a non-zero bounding box.
// Mock it to render children directly.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 300 }}>{children}</div>
    ),
  };
});

const mockUsage = {
  sources: [
    { source: 'console', tokens: 15000, requests: 30 },
    { source: 'portal', tokens: 8000, requests: 12 },
  ],
  total_tokens: 23000,
  total_requests: 42,
  period_days: 7,
};

const mockBudget = {
  daily_budget: 100_000,
  tenant_tokens_today: 23000,
  usage_percent: 23,
  budget_exceeded: false,
  user_tokens_today: 5000,
  remaining: 77000,
};

const mockMetrics = {
  tenant_id: 'test-tenant',
  total_conversations: 45,
  total_messages: 312,
  total_tokens: 23000,
  unique_users: 7,
};

const mockModelDist = {
  models: [
    { model: 'claude-sonnet-4-20250514', conversations: 30 },
    { model: 'claude-haiku-4-5-20251001', conversations: 15 },
  ],
  total_conversations: 45,
};

describe('ChatUsageDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('stoa-active-tenant', 'test-tenant');
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.mocked(apiService.getChatUsageTenant).mockResolvedValue(mockUsage);
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue(mockBudget);
    vi.mocked(apiService.getChatConversationMetrics).mockResolvedValue(mockMetrics);
    vi.mocked(apiService.getChatModelDistribution).mockResolvedValue(mockModelDist);
  });

  it('renders the page header', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalled());
    expect(screen.getByText('Chat Usage')).toBeInTheDocument();
  });

  it('shows tenant ID in header', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalled());
    expect(screen.getByText('test-tenant')).toBeInTheDocument();
  });

  it('renders stat cards with conversation metrics', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByTestId('stat-cards')).toBeInTheDocument());
    expect(screen.getByText('Total Tokens')).toBeInTheDocument();
    expect(screen.getByText('Conversations')).toBeInTheDocument();
    expect(screen.getByText('Messages')).toBeInTheDocument();
    expect(screen.getByText('Active Users')).toBeInTheDocument();
  });

  it('renders period selector buttons with 7 Days default', async () => {
    render(<ChatUsageDashboard />);
    expect(screen.getByTestId('period-1')).toBeInTheDocument();
    expect(screen.getByTestId('period-7')).toBeInTheDocument();
    expect(screen.getByTestId('period-30')).toBeInTheDocument();
  });

  it('fetches data with selected period when clicking 30 Days', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('period-30'));
    await waitFor(() =>
      expect(apiService.getChatUsageTenant).toHaveBeenCalledWith('test-tenant', { days: 30 })
    );
  });

  it('renders source chart section', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByTestId('source-chart')).toBeInTheDocument());
    expect(screen.getByText('Token Usage by App')).toBeInTheDocument();
  });

  it('renders model distribution chart section', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByTestId('model-chart')).toBeInTheDocument());
    expect(screen.getByText('Model Distribution')).toBeInTheDocument();
  });

  it('renders budget section', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByTestId('budget-section')).toBeInTheDocument());
    expect(screen.getByText('Daily Budget')).toBeInTheDocument();
    expect(screen.getByTestId('budget-bar')).toBeInTheDocument();
  });

  it('shows refresh button and calls fetch on click', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalledTimes(2));
  });

  it('shows no-tenant fallback', () => {
    localStorage.removeItem('stoa-active-tenant');
    const mock = createAuthMock('cpi-admin');
    vi.mocked(useAuth).mockReturnValue({
      ...mock,
      user: { ...mock.user, tenant_id: undefined },
    });
    render(<ChatUsageDashboard />);
    expect(screen.getByText(/No tenant selected/i)).toBeInTheDocument();
  });

  it('shows error when usage fetch fails', async () => {
    vi.mocked(apiService.getChatUsageTenant).mockRejectedValue(new Error('network'));
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByText(/Failed to load usage data/i)).toBeInTheDocument());
  });

  it('shows budget exceeded message', async () => {
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue({
      ...mockBudget,
      budget_exceeded: true,
      usage_percent: 100,
    });
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByText(/Daily budget exceeded/i)).toBeInTheDocument());
  });

  it('fetches all 4 endpoints on mount', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => {
      expect(apiService.getChatUsageTenant).toHaveBeenCalledTimes(1);
      expect(apiService.getChatBudgetStatus).toHaveBeenCalledTimes(1);
      expect(apiService.getChatConversationMetrics).toHaveBeenCalledTimes(1);
      expect(apiService.getChatModelDistribution).toHaveBeenCalledTimes(1);
    });
  });

  it('shows empty state for model chart when no conversations', async () => {
    vi.mocked(apiService.getChatModelDistribution).mockResolvedValue({
      models: [],
      total_conversations: 0,
    });
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByText('No conversations yet.')).toBeInTheDocument());
  });

  it('shows empty state for source chart when no tokens', async () => {
    vi.mocked(apiService.getChatUsageTenant).mockResolvedValue({
      sources: [],
      total_tokens: 0,
      total_requests: 0,
      period_days: 7,
    });
    render(<ChatUsageDashboard />);
    await waitFor(() =>
      expect(screen.getByText('No token usage data for this period.')).toBeInTheDocument()
    );
  });
});
