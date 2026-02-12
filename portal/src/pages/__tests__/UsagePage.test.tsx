/**
 * UsagePage Tests - CAB-1133
 *
 * Tests for the usage dashboard showing metrics, calls, and subscriptions.
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { UsagePage } from '../usage/UsagePage';

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock usageService
const mockGetSummary = vi.fn();
const mockGetCalls = vi.fn();
const mockGetActiveSubscriptions = vi.fn();
const mockFormatLatency = vi.fn((ms: number) => `${ms}ms`);

vi.mock('../../services/usage', () => ({
  usageService: {
    getSummary: () => mockGetSummary(),
    getCalls: () => mockGetCalls(),
    getActiveSubscriptions: () => mockGetActiveSubscriptions(),
  },
  formatLatency: (ms: number) => mockFormatLatency(ms),
}));

// Mock usage components as simple stubs
vi.mock('../../components/usage', () => ({
  StatCard: ({ title, value, isLoading }: { title: string; value: string; isLoading: boolean }) => (
    <div data-testid={`stat-card-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      {isLoading ? 'Loading...' : `${title}: ${value}`}
    </div>
  ),
  CallsTable: ({ calls, isLoading }: { calls: unknown[]; isLoading: boolean }) => (
    <div data-testid="calls-table">{isLoading ? 'Loading calls...' : `Calls: ${calls.length}`}</div>
  ),
  UsageChart: ({ data, isLoading }: { data: unknown[]; isLoading: boolean }) => (
    <div data-testid="usage-chart">
      {isLoading ? 'Loading chart...' : `Chart data: ${data.length} points`}
    </div>
  ),
  TopTools: ({ tools, isLoading }: { tools: unknown[]; isLoading: boolean }) => (
    <div data-testid="top-tools">{isLoading ? 'Loading tools...' : `Tools: ${tools.length}`}</div>
  ),
  SubscriptionsList: ({
    subscriptions,
    isLoading,
  }: {
    subscriptions: unknown[];
    isLoading: boolean;
  }) => (
    <div data-testid="subscriptions-list">
      {isLoading ? 'Loading subscriptions...' : `Subscriptions: ${subscriptions.length}`}
    </div>
  ),
}));

describe('UsagePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      accessToken: 'mock-token',
      user: { email: 'test@example.com' },
    });
  });

  it('renders the Usage Dashboard heading', async () => {
    mockGetSummary.mockResolvedValue({
      today: {
        period: 'today',
        total_calls: 150,
        success_count: 142,
        error_count: 8,
        success_rate: 94.7,
        avg_latency_ms: 185,
      },
      this_week: {
        period: 'week',
        total_calls: 1200,
        success_count: 1150,
        error_count: 50,
        success_rate: 95.8,
        avg_latency_ms: 175,
      },
      this_month: {
        period: 'month',
        total_calls: 4500,
        success_count: 4350,
        error_count: 150,
        success_rate: 96.7,
        avg_latency_ms: 190,
      },
      top_tools: [],
      daily_calls: [],
    });
    mockGetCalls.mockResolvedValue({ calls: [] });
    mockGetActiveSubscriptions.mockResolvedValue([]);

    renderWithProviders(<UsagePage />);

    await waitFor(() => {
      expect(screen.getByText('Usage Dashboard')).toBeInTheDocument();
    });
  });

  it('shows error banner when summary fails to load', async () => {
    mockGetSummary.mockRejectedValue(new Error('Network error'));
    mockGetCalls.mockResolvedValue({ calls: [] });
    mockGetActiveSubscriptions.mockResolvedValue([]);

    renderWithProviders(<UsagePage />);

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('renders period selector buttons', async () => {
    mockGetSummary.mockResolvedValue({
      today: {
        period: 'today',
        total_calls: 150,
        success_count: 142,
        error_count: 8,
        success_rate: 94.7,
        avg_latency_ms: 185,
      },
      this_week: {
        period: 'week',
        total_calls: 1200,
        success_count: 1150,
        error_count: 50,
        success_rate: 95.8,
        avg_latency_ms: 175,
      },
      this_month: {
        period: 'month',
        total_calls: 4500,
        success_count: 4350,
        error_count: 150,
        success_rate: 96.7,
        avg_latency_ms: 190,
      },
      top_tools: [],
      daily_calls: [],
    });
    mockGetCalls.mockResolvedValue({ calls: [] });
    mockGetActiveSubscriptions.mockResolvedValue([]);

    renderWithProviders(<UsagePage />);

    await waitFor(() => {
      expect(screen.getByText('Today')).toBeInTheDocument();
      expect(screen.getByText('This Week')).toBeInTheDocument();
      expect(screen.getByText('This Month')).toBeInTheDocument();
    });
  });

  it('renders the Refresh button', async () => {
    mockGetSummary.mockResolvedValue({
      today: {
        period: 'today',
        total_calls: 150,
        success_count: 142,
        error_count: 8,
        success_rate: 94.7,
        avg_latency_ms: 185,
      },
      this_week: {
        period: 'week',
        total_calls: 1200,
        success_count: 1150,
        error_count: 50,
        success_rate: 95.8,
        avg_latency_ms: 175,
      },
      this_month: {
        period: 'month',
        total_calls: 4500,
        success_count: 4350,
        error_count: 150,
        success_rate: 96.7,
        avg_latency_ms: 190,
      },
      top_tools: [],
      daily_calls: [],
    });
    mockGetCalls.mockResolvedValue({ calls: [] });
    mockGetActiveSubscriptions.mockResolvedValue([]);

    renderWithProviders(<UsagePage />);

    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument();
    });
  });

  it('renders four stat cards', async () => {
    mockGetSummary.mockResolvedValue({
      today: {
        period: 'today',
        total_calls: 150,
        success_count: 142,
        error_count: 8,
        success_rate: 94.7,
        avg_latency_ms: 185,
      },
      this_week: {
        period: 'week',
        total_calls: 1200,
        success_count: 1150,
        error_count: 50,
        success_rate: 95.8,
        avg_latency_ms: 175,
      },
      this_month: {
        period: 'month',
        total_calls: 4500,
        success_count: 4350,
        error_count: 150,
        success_rate: 96.7,
        avg_latency_ms: 190,
      },
      top_tools: [],
      daily_calls: [],
    });
    mockGetCalls.mockResolvedValue({ calls: [] });
    mockGetActiveSubscriptions.mockResolvedValue([]);

    renderWithProviders(<UsagePage />);

    await waitFor(() => {
      expect(screen.getByTestId('stat-card-total-calls')).toBeInTheDocument();
      expect(screen.getByTestId('stat-card-success-rate')).toBeInTheDocument();
      expect(screen.getByTestId('stat-card-avg-latency')).toBeInTheDocument();
      expect(screen.getByTestId('stat-card-errors')).toBeInTheDocument();
    });
  });

  it('renders main content components', async () => {
    mockGetSummary.mockResolvedValue({
      today: {
        period: 'today',
        total_calls: 150,
        success_count: 142,
        error_count: 8,
        success_rate: 94.7,
        avg_latency_ms: 185,
      },
      this_week: {
        period: 'week',
        total_calls: 1200,
        success_count: 1150,
        error_count: 50,
        success_rate: 95.8,
        avg_latency_ms: 175,
      },
      this_month: {
        period: 'month',
        total_calls: 4500,
        success_count: 4350,
        error_count: 150,
        success_rate: 96.7,
        avg_latency_ms: 190,
      },
      top_tools: [
        {
          tool_id: 'tool-1',
          tool_name: 'test',
          call_count: 10,
          success_rate: 99,
          avg_latency_ms: 120,
        },
      ],
      daily_calls: [{ date: '2026-02-10', calls: 150 }],
    });
    mockGetCalls.mockResolvedValue({ calls: [{ id: 'call-1' }] });
    mockGetActiveSubscriptions.mockResolvedValue([{ id: 'sub-1' }]);

    renderWithProviders(<UsagePage />);

    await waitFor(() => {
      expect(screen.getByTestId('usage-chart')).toBeInTheDocument();
      expect(screen.getByTestId('calls-table')).toBeInTheDocument();
      expect(screen.getByTestId('top-tools')).toBeInTheDocument();
      expect(screen.getByTestId('subscriptions-list')).toBeInTheDocument();
    });
  });

  it('all four personas can access the usage page', async () => {
    const personas = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'] as const;

    for (const persona of personas) {
      vi.clearAllMocks();
      mockAuth.mockReturnValue({
        isAuthenticated: true,
        isLoading: false,
        accessToken: `mock-token-${persona}`,
        user: { email: `${persona}@example.com` },
      });

      mockGetSummary.mockResolvedValue({
        today: {
          period: 'today',
          total_calls: 150,
          success_count: 142,
          error_count: 8,
          success_rate: 94.7,
          avg_latency_ms: 185,
        },
        this_week: {
          period: 'week',
          total_calls: 1200,
          success_count: 1150,
          error_count: 50,
          success_rate: 95.8,
          avg_latency_ms: 175,
        },
        this_month: {
          period: 'month',
          total_calls: 4500,
          success_count: 4350,
          error_count: 150,
          success_rate: 96.7,
          avg_latency_ms: 190,
        },
        top_tools: [],
        daily_calls: [],
      });
      mockGetCalls.mockResolvedValue({ calls: [] });
      mockGetActiveSubscriptions.mockResolvedValue([]);

      const { unmount } = renderWithProviders(<UsagePage />);

      await waitFor(() => {
        expect(screen.getByText('Usage Dashboard')).toBeInTheDocument();
      });

      unmount();
    }
  });
});
