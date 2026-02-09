import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ShadowDiscovery } from './ShadowDiscovery';

describe('ShadowDiscovery', () => {
  it('renders title and coming soon card', () => {
    render(<ShadowDiscovery />);
    expect(screen.getByText('Shadow API Discovery')).toBeInTheDocument();
    expect(screen.getByText('Coming Soon')).toBeInTheDocument();
  });
});
