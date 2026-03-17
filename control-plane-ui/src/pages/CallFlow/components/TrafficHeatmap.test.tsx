import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TrafficHeatmap } from './TrafficHeatmap';

describe('TrafficHeatmap', () => {
  it('renders empty state with no data', () => {
    render(<TrafficHeatmap cells={[]} routes={[]} />);
    expect(screen.getByText(/no traffic heatmap/i)).toBeInTheDocument();
  });

  it('renders heatmap grid with routes', () => {
    const routes = ['/api/customers', '/api/orders'];
    const cells = [
      { hour: 0, route: '/api/customers', value: 10 },
      { hour: 12, route: '/api/customers', value: 50 },
      { hour: 0, route: '/api/orders', value: 5 },
      { hour: 12, route: '/api/orders', value: 30 },
    ];
    render(<TrafficHeatmap cells={cells} routes={routes} />);
    expect(screen.getByText('/api/customers')).toBeInTheDocument();
    expect(screen.getByText('/api/orders')).toBeInTheDocument();
    expect(screen.getByText('Low')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
  });
});
