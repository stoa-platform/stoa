import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { APICard } from '../APICard';
import { renderWithProviders, mockAPI } from '../../../test/helpers';

describe('APICard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the API name', () => {
    const api = mockAPI();
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('Payment API')).toBeInTheDocument();
  });

  it('renders the API version', () => {
    const api = mockAPI();
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('v2.1.0')).toBeInTheDocument();
  });

  it('renders the API description', () => {
    const api = mockAPI();
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('Process payments securely')).toBeInTheDocument();
  });

  it('renders published status badge', () => {
    const api = mockAPI({ status: 'published' });
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('published')).toBeInTheDocument();
  });

  it('renders deprecated status badge', () => {
    const api = mockAPI({ status: 'deprecated' });
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('deprecated')).toBeInTheDocument();
  });

  it('renders draft status badge', () => {
    const api = mockAPI({ status: 'draft' });
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('draft')).toBeInTheDocument();
  });

  it('renders category tag', () => {
    const api = mockAPI({ category: 'Finance' });
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('Finance')).toBeInTheDocument();
  });

  it('renders first two tags', () => {
    const api = mockAPI({ tags: ['payments', 'fintech', 'banking'] });
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('payments')).toBeInTheDocument();
    expect(screen.getByText('fintech')).toBeInTheDocument();
    expect(screen.getByText('+1')).toBeInTheDocument();
  });

  it('renders View Details link', () => {
    const api = mockAPI();
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('View Details')).toBeInTheDocument();
  });

  it('links to the API detail page', () => {
    const api = mockAPI({ id: 'api-1' });
    const { container } = renderWithProviders(<APICard api={api} />);

    const link = container.querySelector('a');
    expect(link).toHaveAttribute('href', '/apis/api-1');
  });

  it('shows fallback description when none provided', () => {
    const api = mockAPI({ description: '' });
    renderWithProviders(<APICard api={api} />);

    expect(screen.getByText('No description available')).toBeInTheDocument();
  });

  it('renders formatted updated date', () => {
    const api = mockAPI({ updatedAt: '2026-02-01T00:00:00Z' });
    renderWithProviders(<APICard api={api} />);

    // Date should be formatted as "Feb 1, 2026"
    expect(screen.getByText('Feb 1, 2026')).toBeInTheDocument();
  });

  it('calls onMouseEnter handler when provided', () => {
    const api = mockAPI();
    const onMouseEnter = vi.fn();
    const { container } = renderWithProviders(<APICard api={api} onMouseEnter={onMouseEnter} />);

    const link = container.querySelector('a')!;
    fireEvent.mouseEnter(link);

    expect(onMouseEnter).toHaveBeenCalledTimes(1);
  });
});
