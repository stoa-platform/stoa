import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Policies } from './Policies';

describe('Policies', () => {
  it('renders title and coming soon card', () => {
    render(<Policies />);
    expect(screen.getByText('Policies')).toBeInTheDocument();
    expect(screen.getByText('Coming Soon')).toBeInTheDocument();
  });
});
