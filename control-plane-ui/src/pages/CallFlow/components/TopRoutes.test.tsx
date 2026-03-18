import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TopRoutes } from './TopRoutes';

describe('TopRoutes', () => {
  it('renders empty state when no routes', () => {
    render(<TopRoutes routes={[]} />);
    expect(screen.getByText(/no route data/i)).toBeInTheDocument();
  });

  it('renders routes with latency bars', () => {
    const routes = [
      { route: '/api/customers', p95Ms: 120, calls: 500 },
      { route: '/api/orders', p95Ms: 45, calls: 300 },
    ];
    render(<TopRoutes routes={routes} />);
    expect(screen.getByText('/api/customers')).toBeInTheDocument();
    expect(screen.getByText('/api/orders')).toBeInTheDocument();
    expect(screen.getByText('120ms')).toBeInTheDocument();
    expect(screen.getByText('45ms')).toBeInTheDocument();
  });

  it('limits display to 8 routes', () => {
    const routes = Array.from({ length: 12 }, (_, i) => ({
      route: `/api/route-${i}`,
      p95Ms: 10 * (i + 1),
      calls: 100,
    }));
    render(<TopRoutes routes={routes} />);
    expect(screen.getByText('/api/route-0')).toBeInTheDocument();
    expect(screen.getByText('/api/route-7')).toBeInTheDocument();
    expect(screen.queryByText('/api/route-8')).not.toBeInTheDocument();
  });
});
