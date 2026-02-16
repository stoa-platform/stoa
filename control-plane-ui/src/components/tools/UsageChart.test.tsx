import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { UsageChart, UsageStatsCard } from './UsageChart';

const mockData = [
  { timestamp: '2026-02-10', calls: 100, successRate: 0.95, avgLatencyMs: 45, costUnits: 0.005 },
  { timestamp: '2026-02-11', calls: 150, successRate: 0.92, avgLatencyMs: 50, costUnits: 0.008 },
  { timestamp: '2026-02-12', calls: 120, successRate: 0.98, avgLatencyMs: 40, costUnits: 0.006 },
  { timestamp: '2026-02-13', calls: 200, successRate: 0.9, avgLatencyMs: 55, costUnits: 0.01 },
  { timestamp: '2026-02-14', calls: 180, successRate: 0.94, avgLatencyMs: 42, costUnits: 0.009 },
  { timestamp: '2026-02-15', calls: 220, successRate: 0.96, avgLatencyMs: 38, costUnits: 0.011 },
];

describe('UsageChart', () => {
  it('renders empty state when no data', () => {
    render(<UsageChart data={[]} metric="calls" title="API Calls" />);
    expect(screen.getByText('No data available')).toBeInTheDocument();
    expect(screen.getByText('API Calls')).toBeInTheDocument();
  });

  it('renders chart title with data', () => {
    render(<UsageChart data={mockData} metric="calls" title="API Calls" />);
    expect(screen.getByText('API Calls')).toBeInTheDocument();
  });

  it('renders x-axis labels from first and last data points', () => {
    render(<UsageChart data={mockData} metric="calls" title="API Calls" />);
    // First and last labels appear in the x-axis footer
    const labels = screen.getAllByText(/Feb 1/);
    expect(labels.length).toBeGreaterThanOrEqual(1);
  });

  it('renders different metrics', () => {
    const { rerender } = render(
      <UsageChart data={mockData} metric="successRate" title="Success Rate" />
    );
    expect(screen.getByText('Success Rate')).toBeInTheDocument();

    rerender(<UsageChart data={mockData} metric="avgLatencyMs" title="Latency" />);
    expect(screen.getByText('Latency')).toBeInTheDocument();

    rerender(<UsageChart data={mockData} metric="costUnits" title="Cost" />);
    expect(screen.getByText('Cost')).toBeInTheDocument();
  });

  it('computes trend from 6+ data points', () => {
    render(<UsageChart data={mockData} metric="calls" title="API Calls" />);
    // With 6 data points, trend is computed — percentage should be rendered
    const trendEl = screen.getByText(/%$/);
    expect(trendEl).toBeInTheDocument();
  });

  it('renders bars for each data point', () => {
    const { container } = render(<UsageChart data={mockData} metric="calls" title="API Calls" />);
    // Each data point gets a flex-1 column
    const bars = container.querySelectorAll('.bg-blue-500');
    expect(bars.length).toBe(mockData.length);
  });

  it('renders with custom height', () => {
    const { container } = render(
      <UsageChart data={mockData} metric="calls" title="API Calls" height={300} />
    );
    const chartDiv = container.querySelector('[style*="height: 300px"]');
    expect(chartDiv).toBeTruthy();
  });
});

describe('UsageStatsCard', () => {
  it('renders title and value', () => {
    render(<UsageStatsCard title="Total Calls" value="1,234" />);
    expect(screen.getByText('Total Calls')).toBeInTheDocument();
    expect(screen.getByText('1,234')).toBeInTheDocument();
  });

  it('renders subtitle', () => {
    render(<UsageStatsCard title="Calls" value={500} subtitle="Last 7 days" />);
    expect(screen.getByText('Last 7 days')).toBeInTheDocument();
  });

  it('renders positive trend', () => {
    render(<UsageStatsCard title="Calls" value={500} trend={12.5} />);
    expect(screen.getByText('12.5%')).toBeInTheDocument();
  });

  it('renders negative trend', () => {
    render(<UsageStatsCard title="Calls" value={500} trend={-5.2} />);
    expect(screen.getByText('5.2%')).toBeInTheDocument();
  });

  it('renders with icon', () => {
    const icon = <span data-testid="custom-icon">Icon</span>;
    render(<UsageStatsCard title="Calls" value={500} icon={icon} />);
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('renders with different colors', () => {
    const { container } = render(
      <UsageStatsCard title="Calls" value={500} icon={<span>I</span>} color="green" />
    );
    const iconWrapper = container.querySelector('.bg-green-50');
    expect(iconWrapper).toBeTruthy();
  });
});
