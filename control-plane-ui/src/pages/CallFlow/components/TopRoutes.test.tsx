import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TopRoutes } from './TopRoutes';

// Mock recharts — JSDOM has no layout engine so Recharts hooks fail.
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  BarChart: ({ children, data }: { children: React.ReactNode; data: unknown[] }) => (
    <svg data-testid="bar-chart" data-count={data.length}>
      {children}
    </svg>
  ),
  Bar: () => <rect data-testid="bar" />,
  Cell: () => <rect data-testid="cell" />,
  XAxis: () => <g data-testid="x-axis" />,
  YAxis: () => <g data-testid="y-axis" />,
  CartesianGrid: () => <g data-testid="grid" />,
  Tooltip: () => <g data-testid="tooltip" />,
}));

describe('TopRoutes', () => {
  it('renders empty state when no routes', () => {
    render(<TopRoutes routes={[]} />);
    expect(screen.getByText(/no route data/i)).toBeInTheDocument();
  });

  it('renders Recharts BarChart with routes', () => {
    const routes = [
      { route: '/api/customers', p95Ms: 120, calls: 500 },
      { route: '/api/orders', p95Ms: 45, calls: 300 },
    ];
    render(<TopRoutes routes={routes} />);
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
    expect(screen.getByTestId('bar-chart')).toHaveAttribute('data-count', '2');
  });

  it('limits data to 8 routes', () => {
    const routes = Array.from({ length: 12 }, (_, i) => ({
      route: `/api/route-${i}`,
      p95Ms: 10 * (i + 1),
      calls: 100,
    }));
    render(<TopRoutes routes={routes} />);
    expect(screen.getByTestId('bar-chart')).toHaveAttribute('data-count', '8');
  });
});
