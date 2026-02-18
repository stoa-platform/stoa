import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { Footer } from '../Footer';
import { renderWithProviders } from '../../../test/helpers';

vi.mock('../../../config', () => ({
  config: {
    services: {
      docs: { url: 'https://docs.gostoa.dev' },
    },
    app: {
      version: '1.0.0',
    },
  },
}));

describe('Footer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders copyright text', () => {
    renderWithProviders(<Footer />);

    expect(screen.getByText(/STOA Platform/)).toBeInTheDocument();
    expect(screen.getByText(/All rights reserved/)).toBeInTheDocument();
  });

  it('renders current year in copyright', () => {
    renderWithProviders(<Footer />);

    const year = new Date().getFullYear().toString();
    expect(screen.getByText(new RegExp(year))).toBeInTheDocument();
  });

  it('renders Documentation link', () => {
    renderWithProviders(<Footer />);

    const docsLink = screen.getByText('Documentation');
    expect(docsLink).toBeInTheDocument();
  });

  it('renders Documentation link that opens in new tab', () => {
    renderWithProviders(<Footer />);

    const docsLink = screen.getByText('Documentation').closest('a');
    expect(docsLink).toHaveAttribute('target', '_blank');
    expect(docsLink).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('renders app version', () => {
    renderWithProviders(<Footer />);

    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
  });
});
