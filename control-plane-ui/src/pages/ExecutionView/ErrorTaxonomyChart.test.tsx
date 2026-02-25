import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ErrorTaxonomyChart } from './ErrorTaxonomyChart';

describe('ErrorTaxonomyChart', () => {
  it('renders empty state when no items', () => {
    render(<ErrorTaxonomyChart items={[]} totalErrors={0} />);
    expect(screen.getByText('No error data available')).toBeInTheDocument();
  });

  it('renders bars for each category', () => {
    const items = [
      { category: 'auth', count: 50, avg_duration_ms: 120, percentage: 50 },
      { category: 'timeout', count: 30, avg_duration_ms: 500, percentage: 30 },
      { category: 'validation', count: 20, avg_duration_ms: 80, percentage: 20 },
    ];
    render(<ErrorTaxonomyChart items={items} totalErrors={100} />);

    expect(screen.getByText('Auth')).toBeInTheDocument();
    expect(screen.getByText('Timeout')).toBeInTheDocument();
    expect(screen.getByText('Validation')).toBeInTheDocument();
  });

  it('shows counts for each category', () => {
    const items = [
      { category: 'auth', count: 50, avg_duration_ms: 120, percentage: 50 },
      { category: 'backend', count: 25, avg_duration_ms: 200, percentage: 25 },
    ];
    render(<ErrorTaxonomyChart items={items} totalErrors={75} />);

    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
  });

  it('shows total errors summary', () => {
    const items = [{ category: 'auth', count: 10, avg_duration_ms: 100, percentage: 100 }];
    render(<ErrorTaxonomyChart items={items} totalErrors={10} />);

    expect(screen.getByText('10 total errors across 1 categories')).toBeInTheDocument();
  });

  it('shows percentages', () => {
    const items = [
      { category: 'rate_limit', count: 40, avg_duration_ms: null, percentage: 66.7 },
      { category: 'backend', count: 20, avg_duration_ms: 300, percentage: 33.3 },
    ];
    render(<ErrorTaxonomyChart items={items} totalErrors={60} />);

    expect(screen.getByText('66.7%')).toBeInTheDocument();
    expect(screen.getByText('33.3%')).toBeInTheDocument();
  });

  it('renders SVG bars with aria labels', () => {
    const items = [{ category: 'auth', count: 10, avg_duration_ms: 100, percentage: 100 }];
    render(<ErrorTaxonomyChart items={items} totalErrors={10} />);

    const svg = screen.getByRole('img');
    expect(svg).toHaveAttribute('aria-label', 'Auth: 10');
  });

  it('handles unknown category gracefully', () => {
    const items = [{ category: 'unknown_error', count: 5, avg_duration_ms: 50, percentage: 100 }];
    render(<ErrorTaxonomyChart items={items} totalErrors={5} />);

    expect(screen.getByText('unknown_error')).toBeInTheDocument();
  });
});
