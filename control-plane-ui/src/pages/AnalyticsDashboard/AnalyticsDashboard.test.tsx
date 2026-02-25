import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

vi.mock('../../hooks/usePrometheus', () => ({
  usePrometheusQuery: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  usePrometheusRange: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  scalarValue: vi.fn(() => null),
  groupByLabel: vi.fn(() => ({})),
}));

vi.mock('../../components/charts/SparklineChart', () => ({
  SparklineChart: () => <div data-testid="sparkline-chart">Sparkline</div>,
}));

describe('AnalyticsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

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
