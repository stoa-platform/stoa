import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TokenOptimizer } from './TokenOptimizer';

describe('TokenOptimizer', () => {
  it('renders title and coming soon card', () => {
    render(<TokenOptimizer />);
    expect(screen.getByText('Token Optimizer')).toBeInTheDocument();
    expect(screen.getByText('Coming Soon')).toBeInTheDocument();
  });
});
