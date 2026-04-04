/**
 * Tests for UsageChart (CAB-1390, updated for Recharts migration CAB-1883)
 */

import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { UsageChart } from './UsageChart';
import { renderWithProviders } from '../../test/helpers';
import type { DailyCallStat } from '../../types';

// Mock recharts — JSDOM has no layout engine so Recharts hooks fail.
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <svg data-testid="bar-chart">{children}</svg>
  ),
  Bar: () => <rect data-testid="bar" />,
  Cell: () => <rect data-testid="cell" />,
  XAxis: () => <g data-testid="x-axis" />,
  YAxis: () => <g data-testid="y-axis" />,
  CartesianGrid: () => <g data-testid="grid" />,
  Tooltip: () => <g data-testid="tooltip" />,
}));

const mockData: DailyCallStat[] = [
  { date: '2026-02-15', calls: 100 },
  { date: '2026-02-16', calls: 200 },
  { date: '2026-02-17', calls: 150 },
];

describe('UsageChart', () => {
  it('shows loading skeleton when isLoading is true', () => {
    const { container } = renderWithProviders(<UsageChart data={[]} isLoading={true} />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('does not show loading skeleton when isLoading is false', () => {
    const { container } = renderWithProviders(<UsageChart data={mockData} isLoading={false} />);
    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
  });

  it('renders empty state when data is empty', () => {
    renderWithProviders(<UsageChart data={[]} />);
    expect(screen.getByText('No call data available')).toBeInTheDocument();
  });

  it('renders Recharts BarChart with data', () => {
    renderWithProviders(<UsageChart data={mockData} />);
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
  });

  it('renders total calls count', () => {
    renderWithProviders(<UsageChart data={mockData} />);
    expect(screen.getByText(/Total: 450 calls/)).toBeInTheDocument();
  });

  it('renders chart title', () => {
    renderWithProviders(<UsageChart data={mockData} />);
    expect(screen.getByText('Call Volume (7 days)')).toBeInTheDocument();
  });
});
