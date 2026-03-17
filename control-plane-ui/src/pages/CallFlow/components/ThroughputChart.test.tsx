import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThroughputChart } from './ThroughputChart';

describe('ThroughputChart', () => {
  it('renders empty state when no data', () => {
    render(<ThroughputChart series={[]} timeRange="1h" />);
    expect(screen.getByText(/no throughput data/i)).toBeInTheDocument();
  });

  it('renders empty state with null series data', () => {
    const series = [{ label: 'Gateway', color: '#3274D9', data: null }];
    render(<ThroughputChart series={series} timeRange="1h" />);
    expect(screen.getByText(/no throughput data/i)).toBeInTheDocument();
  });

  it('renders chart container when data is provided', () => {
    const now = Math.floor(Date.now() / 1000);
    const series = [
      {
        label: 'Gateway',
        color: '#3274D9',
        data: [
          { timestamp: now - 300, value: 10 },
          { timestamp: now - 240, value: 15 },
          { timestamp: now - 180, value: 12 },
        ],
      },
    ];
    const { container } = render(<ThroughputChart series={series} timeRange="1h" />);
    // ResponsiveContainer renders even if it doesn't measure dimensions in jsdom
    expect(container.querySelector('[class*="recharts"]')).not.toBeNull();
  });
});
