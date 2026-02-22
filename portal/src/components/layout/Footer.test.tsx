/**
 * Tests for Footer (CAB-1390)
 */

import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { Footer } from './Footer';
import { renderWithProviders } from '../../test/helpers';

vi.mock('../../config', () => ({
  config: {
    app: { version: '1.2.3' },
    services: { docs: { url: 'https://docs.example.com' } },
  },
}));

describe('Footer', () => {
  it('renders the STOA Platform copyright notice', () => {
    renderWithProviders(<Footer />);
    expect(screen.getByText(/STOA Platform/)).toBeInTheDocument();
  });

  it('renders the current year', () => {
    renderWithProviders(<Footer />);
    const year = new Date().getFullYear().toString();
    expect(screen.getByText(new RegExp(year))).toBeInTheDocument();
  });

  it('renders the Documentation link', () => {
    renderWithProviders(<Footer />);
    const link = screen.getByRole('link', { name: 'Documentation' });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', 'https://docs.example.com');
  });

  it('renders the version number', () => {
    renderWithProviders(<Footer />);
    expect(screen.getByText('v1.2.3')).toBeInTheDocument();
  });

  it('renders as a footer element', () => {
    renderWithProviders(<Footer />);
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });
});
