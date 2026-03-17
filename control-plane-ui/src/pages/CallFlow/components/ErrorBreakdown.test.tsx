import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ErrorBreakdown } from './ErrorBreakdown';

describe('ErrorBreakdown', () => {
  it('renders empty state when no errors', () => {
    render(<ErrorBreakdown errors={[]} />);
    expect(screen.getByText(/no errors in this period/i)).toBeInTheDocument();
  });

  it('renders empty state when all counts are zero', () => {
    const errors = [{ code: '500', count: 0 }];
    render(<ErrorBreakdown errors={errors} />);
    expect(screen.getByText(/no errors in this period/i)).toBeInTheDocument();
  });

  it('renders chart with error data', () => {
    const errors = [
      { code: '500', count: 10 },
      { code: '502', count: 5 },
      { code: '404', count: 3 },
    ];
    const { container } = render(<ErrorBreakdown errors={errors} />);
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument();
  });
});
