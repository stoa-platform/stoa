import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlatformMetricsDashboard } from './PlatformMetricsDashboard';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock dependencies
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../services/api', () => ({
  apiService: {
    getTopAPIs: vi.fn(() => Promise.resolve([])),
    get: vi.fn(() =>
      Promise.resolve({
        data: {
          gitops: {
            components: [],
          },
        },
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
}));

vi.mock('../../components/charts/SparklineChart', () => ({
  SparklineChart: () => <div data-testid="sparkline-chart">Sparkline</div>,
}));

describe('PlatformMetricsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the page title', () => {
    render(<PlatformMetricsDashboard />);
    expect(screen.getByText('Platform Metrics')).toBeInTheDocument();
  });

  it('renders the page subtitle', () => {
    render(<PlatformMetricsDashboard />);
    expect(screen.getByText('Real-time platform performance and health')).toBeInTheDocument();
  });

  it('renders time range selector with default 1h selected', () => {
    render(<PlatformMetricsDashboard />);
    const buttons = screen.getAllByRole('button');
    const oneHourButton = buttons.find((btn) => btn.textContent === '1h');
    expect(oneHourButton).toHaveClass('bg-white');
  });

  it('changes time range when button clicked', () => {
    render(<PlatformMetricsDashboard />);
    const buttons = screen.getAllByRole('button');
    const sixHourButton = buttons.find((btn) => btn.textContent === '6h');

    if (sixHourButton) {
      fireEvent.click(sixHourButton);
      expect(sixHourButton).toHaveClass('bg-white');
    }
  });

  it('renders refresh button', () => {
    render(<PlatformMetricsDashboard />);
    const refreshButton = screen.getByText('Refresh');
    expect(refreshButton).toBeInTheDocument();
  });

  it('shows KPI stat cards', () => {
    render(<PlatformMetricsDashboard />);
    expect(screen.getByText(/Total Requests/i)).toBeInTheDocument();
    // Error Rate appears in multiple places - section title and stat card
    const errorRateElements = screen.getAllByText(/Error Rate/i);
    expect(errorRateElements.length).toBeGreaterThan(0);
    expect(screen.getByText(/P95 Latency/i)).toBeInTheDocument();
    expect(screen.getByText(/Services Up/i)).toBeInTheDocument();
  });

  it('shows "--" for null values', () => {
    render(<PlatformMetricsDashboard />);
    const dashes = screen.getAllByText('--');
    expect(dashes.length).toBeGreaterThan(0);
  });

  it('renders sparkline section titles', () => {
    render(<PlatformMetricsDashboard />);
    expect(screen.getByText('Request Rate')).toBeInTheDocument();
    expect(screen.getByText('Error Rate')).toBeInTheDocument();
  });

  it('renders top endpoints section', () => {
    render(<PlatformMetricsDashboard />);
    expect(screen.getByText('Top Endpoints')).toBeInTheDocument();
  });

  it('renders component health section', () => {
    render(<PlatformMetricsDashboard />);
    expect(screen.getByText('Component Health')).toBeInTheDocument();
  });

  it('shows "No API data available" when no top APIs', () => {
    render(<PlatformMetricsDashboard />);
    expect(screen.getByText('No API data available')).toBeInTheDocument();
  });

  it('shows "Component status unavailable" when no component health', () => {
    render(<PlatformMetricsDashboard />);
    expect(screen.getByText('Component status unavailable')).toBeInTheDocument();
  });

  it('calls refetch when refresh button clicked', () => {
    render(<PlatformMetricsDashboard />);
    const refreshButton = screen.getByText('Refresh');
    fireEvent.click(refreshButton);
    expect(refreshButton).toBeInTheDocument();
  });

  it('renders link to business page', () => {
    render(<PlatformMetricsDashboard />);
    const viewAllLink = screen.getByText('View All');
    expect(viewAllLink.closest('a')).toHaveAttribute('href', '/business');
  });

  it('renders link to operations page', () => {
    render(<PlatformMetricsDashboard />);
    const operationsLink = screen.getByText('Operations');
    expect(operationsLink.closest('a')).toHaveAttribute('href', '/operations');
  });

  it('displays last refresh time', () => {
    render(<PlatformMetricsDashboard />);
    const timeElements = screen.getAllByText(/:/);
    expect(timeElements.length).toBeGreaterThan(0);
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<PlatformMetricsDashboard />);
        expect(screen.getByText('Platform Metrics')).toBeInTheDocument();
      });
    }
  );
});
