import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AnalyticsDashboard } from './AnalyticsDashboard';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../services/api', () => ({
  apiService: {
    getTopAPIs: vi.fn(() => Promise.resolve([])),
    get: vi.fn(() =>
      Promise.resolve({
        data: { items: [], total_errors: 0, error_rate: 0 },
      })
    ),
  },
}));

const mockRefetch = vi.fn();

vi.mock('../../hooks/usePrometheus', () => ({
  usePrometheusQuery: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: mockRefetch,
  })),
  usePrometheusRange: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: mockRefetch,
  })),
  scalarValue: vi.fn((results: { value?: [number, string] }[] | null) => {
    if (!results || results.length === 0) return null;
    const val = results[0]?.value?.[1];
    if (val === undefined) return null;
    const n = parseFloat(val);
    return isNaN(n) ? null : n;
  }),
  groupByLabel: vi.fn(
    (
      results: { metric: Record<string, string>; value?: [number, string] }[] | null,
      label: string
    ) => {
      if (!results) return {};
      const groups: Record<string, number> = {};
      for (const r of results) {
        const key = r.metric[label] || 'unknown';
        groups[key] = (groups[key] || 0) + parseFloat(r.value?.[1] || '0');
      }
      return groups;
    }
  ),
}));

vi.mock('../../components/charts/SparklineChart', () => ({
  SparklineChart: () => <div data-testid="sparkline-chart">Sparkline</div>,
}));

import { usePrometheusQuery } from '../../hooks/usePrometheus';

function makeResults(entries: Record<string, number>, label = 'tool') {
  return Object.entries(entries).map(([key, val]) => ({
    metric: { [label]: key },
    value: [Date.now() / 1000, String(val)] as [number, string],
  }));
}

/** Configure usePrometheusQuery to return tool + consumer data based on query content */
function mockWithToolData(toolData: Record<string, number>) {
  const toolResults = makeResults(toolData);
  // agent-alpha: 30/500 = 6% (> 5% -> red), agent-beta: 2/120 = 1.67% (yellow)
  const consumerResults = makeResults({ 'agent-alpha': 500, 'agent-beta': 120 }, 'consumer_id');
  const consumerErrors = makeResults({ 'agent-alpha': 30, 'agent-beta': 2 }, 'consumer_id');
  const consumerLatency = makeResults({ 'agent-alpha': 0.35, 'agent-beta': 0.12 }, 'consumer_id');
  const empty = { data: null, loading: false, error: null, refetch: mockRefetch };
  const withData = (data: unknown) => ({
    data,
    loading: false,
    error: null,
    refetch: mockRefetch,
  });

  vi.mocked(usePrometheusQuery).mockImplementation((query: string) => {
    if (!query) return empty as ReturnType<typeof usePrometheusQuery>;
    // Tool queries (by label "tool")
    if (query.includes('sum by (tool)') && query.includes('status="error"'))
      return withData(toolResults) as ReturnType<typeof usePrometheusQuery>;
    if (query.includes('sum by (tool)') && query.includes('duration_seconds'))
      return withData(toolResults) as ReturnType<typeof usePrometheusQuery>;
    if (query.includes('topk(10, sum by (tool)'))
      return withData(toolResults) as ReturnType<typeof usePrometheusQuery>;
    // Consumer queries (by label "consumer_id")
    if (query.includes('sum by (consumer_id)') && query.includes('status="error"'))
      return withData(consumerErrors) as ReturnType<typeof usePrometheusQuery>;
    if (query.includes('sum by (consumer_id)') && query.includes('duration_seconds'))
      return withData(consumerLatency) as ReturnType<typeof usePrometheusQuery>;
    if (query.includes('topk(10, sum by (consumer_id)'))
      return withData(consumerResults) as ReturnType<typeof usePrometheusQuery>;
    return empty as ReturnType<typeof usePrometheusQuery>;
  });
}

describe('AnalyticsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  // --- Basic rendering ---

  it('renders the page title', () => {
    render(<AnalyticsDashboard />);
    expect(screen.getByText('Usage Analytics')).toBeInTheDocument();
  });

  it('renders time range selector with default 24h selected', () => {
    render(<AnalyticsDashboard />);
    const buttons = screen.getAllByRole('button');
    const dayButton = buttons.find((btn) => btn.textContent === '24h');
    expect(dayButton).toHaveClass('bg-white');
  });

  it('changes time range when button clicked', () => {
    render(<AnalyticsDashboard />);
    const buttons = screen.getAllByRole('button');
    const oneHourButton = buttons.find((btn) => btn.textContent === '1h');
    if (oneHourButton) {
      fireEvent.click(oneHourButton);
      expect(oneHourButton).toHaveClass('bg-white');
    }
  });

  it('renders refresh button', () => {
    render(<AnalyticsDashboard />);
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('shows KPI stat cards after loading', async () => {
    render(<AnalyticsDashboard />);
    await waitFor(() => {
      expect(screen.getByText(/Total Calls/i)).toBeInTheDocument();
      expect(screen.getByText(/Avg Latency/i)).toBeInTheDocument();
      expect(screen.getByText(/Error Rate/i)).toBeInTheDocument();
      expect(screen.getByText(/Active Consumers/i)).toBeInTheDocument();
    });
  });

  it('shows "--" for null values', async () => {
    render(<AnalyticsDashboard />);
    await waitFor(() => {
      const dashes = screen.getAllByText('--');
      expect(dashes.length).toBeGreaterThan(0);
    });
  });

  it('renders chart section titles', async () => {
    render(<AnalyticsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Call Volume')).toBeInTheDocument();
      expect(screen.getByText('Latency Trend')).toBeInTheDocument();
    });
  });

  it('shows empty state for tools and errors', async () => {
    render(<AnalyticsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('No usage data')).toBeInTheDocument();
      expect(screen.getByText('No errors')).toBeInTheDocument();
    });
  });

  it('shows all time range options', () => {
    render(<AnalyticsDashboard />);
    expect(screen.getByText('1h')).toBeInTheDocument();
    expect(screen.getByText('6h')).toBeInTheDocument();
    expect(screen.getByText('24h')).toBeInTheDocument();
    expect(screen.getByText('7d')).toBeInTheDocument();
    expect(screen.getByText('30d')).toBeInTheDocument();
  });

  it('renders consumer activity section', () => {
    render(<AnalyticsDashboard />);
    expect(screen.getByText('Consumer Activity')).toBeInTheDocument();
  });

  it('shows empty consumer state when no data', () => {
    render(<AnalyticsDashboard />);
    expect(screen.getByText('No consumer data')).toBeInTheDocument();
  });

  // --- Sort controls ---

  it('renders sort controls (calls, errors, latency)', () => {
    render(<AnalyticsDashboard />);
    const sortGroup = screen.getByRole('group', { name: /sort tools by/i });
    expect(within(sortGroup).getByLabelText('Sort by calls')).toBeInTheDocument();
    expect(within(sortGroup).getByLabelText('Sort by errors')).toBeInTheDocument();
    expect(within(sortGroup).getByLabelText('Sort by latency')).toBeInTheDocument();
  });

  it('highlights the active sort button (calls by default)', () => {
    render(<AnalyticsDashboard />);
    const callsBtn = screen.getByLabelText('Sort by calls');
    expect(callsBtn.className).toContain('bg-blue-100');
  });

  it('switches active sort when errors clicked', () => {
    render(<AnalyticsDashboard />);
    const errorsBtn = screen.getByLabelText('Sort by errors');
    fireEvent.click(errorsBtn);
    expect(errorsBtn.className).toContain('bg-blue-100');
    const callsBtn = screen.getByLabelText('Sort by calls');
    expect(callsBtn.className).not.toContain('bg-blue-100');
  });

  // --- Tool expansion ---

  it('expands tool detail panel on click', () => {
    mockWithToolData({ 'weather-api': 100, 'search-api': 50 });
    render(<AnalyticsDashboard />);
    const toolButton = screen.getByLabelText('Tool weather-api');
    fireEvent.click(toolButton);
    expect(screen.getByTestId('tool-detail-panel')).toBeInTheDocument();
    expect(screen.getByText('Latency Percentiles')).toBeInTheDocument();
  });

  it('collapses tool detail on second click', () => {
    mockWithToolData({ 'weather-api': 100 });
    render(<AnalyticsDashboard />);
    const toolButton = screen.getByLabelText('Tool weather-api');
    fireEvent.click(toolButton);
    expect(screen.getByTestId('tool-detail-panel')).toBeInTheDocument();
    fireEvent.click(toolButton);
    expect(screen.queryByTestId('tool-detail-panel')).not.toBeInTheDocument();
  });

  it('shows p50/p95/p99 labels in expanded panel', () => {
    mockWithToolData({ 'weather-api': 100 });
    render(<AnalyticsDashboard />);
    fireEvent.click(screen.getByLabelText('Tool weather-api'));
    expect(screen.getByText('p50')).toBeInTheDocument();
    expect(screen.getByText('p95')).toBeInTheDocument();
    expect(screen.getByText('p99')).toBeInTheDocument();
  });

  it('shows error count badge when tool has errors', () => {
    mockWithToolData({ 'flaky-tool': 200 });
    render(<AnalyticsDashboard />);
    const errBadges = screen.getAllByText(/err/);
    expect(errBadges.length).toBeGreaterThan(0);
  });

  it('shows latency badge when tool has latency data', () => {
    mockWithToolData({ 'slow-tool': 80 });
    render(<AnalyticsDashboard />);
    const latencyBadges = screen.getAllByText(/ms$/);
    expect(latencyBadges.length).toBeGreaterThan(0);
  });

  // --- Consumer table ---

  it('renders consumer table with data', () => {
    mockWithToolData({ 'test-tool': 50 });
    render(<AnalyticsDashboard />);
    expect(screen.getByText('agent-alpha')).toBeInTheDocument();
    expect(screen.getByText('agent-beta')).toBeInTheDocument();
  });

  it('shows consumer table headers', () => {
    mockWithToolData({ 'test-tool': 50 });
    render(<AnalyticsDashboard />);
    expect(screen.getByText('Consumer')).toBeInTheDocument();
    expect(screen.getByText('Calls')).toBeInTheDocument();
    expect(screen.getByText('Avg Latency')).toBeInTheDocument();
  });

  it('color-codes high error rate consumers red', () => {
    mockWithToolData({ 'test-tool': 50 });
    render(<AnalyticsDashboard />);
    // agent-alpha: 30/500 = 6% (> 5% -> red)
    const alphaRow = screen.getByText('agent-alpha').closest('tr')!;
    const errorCell = within(alphaRow).getByText('6.0%');
    expect(errorCell.className).toContain('text-red-600');
  });

  it('color-codes low error rate consumers green-or-yellow', () => {
    mockWithToolData({ 'test-tool': 50 });
    render(<AnalyticsDashboard />);
    // agent-beta: 2/120 = 1.67% (between 1% and 5% -> yellow)
    const betaRow = screen.getByText('agent-beta').closest('tr')!;
    const errorCell = within(betaRow).getByText('1.7%');
    expect(errorCell.className).toContain('text-yellow-600');
  });

  // --- Refresh ---

  it('calls refetch on refresh click', () => {
    render(<AnalyticsDashboard />);
    fireEvent.click(screen.getByText('Refresh'));
    expect(mockRefetch).toHaveBeenCalled();
  });

  // --- Persona tests ---

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<AnalyticsDashboard />);
        expect(screen.getByText('Usage Analytics')).toBeInTheDocument();
      });
    }
  );
});
