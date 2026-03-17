import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LatencyHistogram } from './LatencyHistogram';

describe('LatencyHistogram', () => {
  it('renders empty state when no buckets', () => {
    render(<LatencyHistogram buckets={[]} />);
    expect(screen.getByText(/no latency distribution/i)).toBeInTheDocument();
  });

  it('renders empty state when all counts are zero', () => {
    const buckets = [
      { label: '0-1ms', count: 0 },
      { label: '1-2ms', count: 0 },
    ];
    render(<LatencyHistogram buckets={buckets} />);
    expect(screen.getByText(/no latency distribution/i)).toBeInTheDocument();
  });

  it('renders chart when buckets have data', () => {
    const buckets = [
      { label: '0-1ms', count: 100 },
      { label: '1-2ms', count: 50 },
      { label: '2-5ms', count: 20 },
    ];
    const { container } = render(<LatencyHistogram buckets={buckets} />);
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument();
  });
});
