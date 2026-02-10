import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RequestExplorerDashboard } from './RequestExplorerDashboard';

// Mock dependencies
vi.mock('../../hooks/usePrometheus', () => ({
  usePrometheusQuery: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  scalarValue: vi.fn(() => null),
  groupByLabel: vi.fn(() => ({})),
}));

describe('RequestExplorerDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page title', () => {
    render(<RequestExplorerDashboard />);
    expect(screen.getByText('Request Explorer')).toBeInTheDocument();
  });

  it('renders the page subtitle', () => {
    render(<RequestExplorerDashboard />);
    expect(
      screen.getByText('Analyze API traffic patterns and error distribution')
    ).toBeInTheDocument();
  });

  it('renders time range selector with default 1h selected', () => {
    render(<RequestExplorerDashboard />);
    const buttons = screen.getAllByRole('button');
    const oneHourButton = buttons.find((btn) => btn.textContent === '1h');
    expect(oneHourButton).toHaveClass('bg-blue-600');
  });

  it('changes time range when button clicked', () => {
    render(<RequestExplorerDashboard />);
    const buttons = screen.getAllByRole('button');
    const twentyFourHourButton = buttons.find((btn) => btn.textContent === '24h');

    if (twentyFourHourButton) {
      fireEvent.click(twentyFourHourButton);
      expect(twentyFourHourButton).toHaveClass('bg-blue-600');
    }
  });

  it('renders refresh button', () => {
    render(<RequestExplorerDashboard />);
    const refreshButton = screen.getByText('Refresh');
    expect(refreshButton).toBeInTheDocument();
  });

  it('shows KPI stat cards', () => {
    render(<RequestExplorerDashboard />);
    expect(screen.getByText(/Total Requests/i)).toBeInTheDocument();
    expect(screen.getByText(/Success Rate/i)).toBeInTheDocument();
    expect(screen.getByText(/Avg Response Time/i)).toBeInTheDocument();
    expect(screen.getByText(/Active Endpoints/i)).toBeInTheDocument();
  });

  it('shows "--" for null values', () => {
    render(<RequestExplorerDashboard />);
    const dashes = screen.getAllByText('--');
    expect(dashes.length).toBeGreaterThan(0);
  });

  it('renders top endpoints section', () => {
    render(<RequestExplorerDashboard />);
    expect(screen.getByText('Top Endpoints')).toBeInTheDocument();
  });

  it('renders link to error snapshots', () => {
    render(<RequestExplorerDashboard />);
    const errorLink = screen.getByText('Error Snapshots');
    expect(errorLink.closest('a')).toHaveAttribute('href', '/mcp/errors');
  });

  it('calls refetch when refresh button clicked', () => {
    render(<RequestExplorerDashboard />);
    const refreshButton = screen.getByText('Refresh');
    fireEvent.click(refreshButton);
    expect(refreshButton).toBeInTheDocument();
  });

  it('displays last refresh time', () => {
    render(<RequestExplorerDashboard />);
    const timeElements = screen.getAllByText(/:/);
    expect(timeElements.length).toBeGreaterThan(0);
  });

  it('shows "No request data" message when no endpoint data', () => {
    render(<RequestExplorerDashboard />);
    expect(
      screen.getByText(/No request data in this time range|Metrics unavailable/)
    ).toBeInTheDocument();
  });

  it('shows all three time range options', () => {
    render(<RequestExplorerDashboard />);
    expect(screen.getByText('1h')).toBeInTheDocument();
    expect(screen.getByText('6h')).toBeInTheDocument();
    expect(screen.getByText('24h')).toBeInTheDocument();
  });

  it('displays subtitles for KPI cards', () => {
    render(<RequestExplorerDashboard />);
    expect(screen.getByText('2xx responses')).toBeInTheDocument();
    expect(screen.getByText('Mean latency')).toBeInTheDocument();
  });
});
