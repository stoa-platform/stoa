import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SkipLink } from './SkipLink';

describe('SkipLink', () => {
  it('should render a link to #main-content', () => {
    render(<SkipLink />);
    const link = screen.getByText('Skip to main content');
    expect(link.tagName).toBe('A');
    expect(link.getAttribute('href')).toBe('#main-content');
  });

  it('should have sr-only class for screen reader visibility', () => {
    render(<SkipLink />);
    const link = screen.getByText('Skip to main content');
    expect(link.className).toContain('sr-only');
  });
});
