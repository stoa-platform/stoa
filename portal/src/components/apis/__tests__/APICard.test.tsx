/**
 * APICard Tests (CAB-1390)
 *
 * Tests for the API catalog card component — display, status badges, tags, and navigation.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { APICard } from '../APICard';
import { renderWithProviders } from '../../../test/helpers';
import type { API } from '../../../types';

const mockAPI: API = {
  id: 'api-001',
  name: 'Payments API',
  version: '2.1.0',
  description: 'Process payments securely',
  category: 'Finance',
  tags: ['payments', 'stripe', 'billing'],
  tenantId: 'tenant-001',
  status: 'published',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-02-01T00:00:00Z',
};

describe('APICard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the API name', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    expect(screen.getByText('Payments API')).toBeInTheDocument();
  });

  it('renders the API version', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    expect(screen.getByText('v2.1.0')).toBeInTheDocument();
  });

  it('renders the description', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    expect(screen.getByText('Process payments securely')).toBeInTheDocument();
  });

  it('renders fallback text when description is empty', () => {
    const api = { ...mockAPI, description: '' };
    renderWithProviders(<APICard api={api} />);
    expect(screen.getByText('No description available')).toBeInTheDocument();
  });

  it('renders "published" status badge', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    expect(screen.getByText('published')).toBeInTheDocument();
  });

  it('renders "deprecated" status badge', () => {
    const api = { ...mockAPI, status: 'deprecated' as const };
    renderWithProviders(<APICard api={api} />);
    expect(screen.getByText('deprecated')).toBeInTheDocument();
  });

  it('renders "draft" status badge', () => {
    const api = { ...mockAPI, status: 'draft' as const };
    renderWithProviders(<APICard api={api} />);
    expect(screen.getByText('draft')).toBeInTheDocument();
  });

  it('renders the category tag', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    expect(screen.getByText('Finance')).toBeInTheDocument();
  });

  it('renders only the first 2 tags', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    expect(screen.getByText('payments')).toBeInTheDocument();
    expect(screen.getByText('stripe')).toBeInTheDocument();
    expect(screen.queryByText('billing')).not.toBeInTheDocument();
  });

  it('renders "+N more" badge when tags exceed 2', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    expect(screen.getByText('+1')).toBeInTheDocument();
  });

  it('does not render "+N more" when tags are 2 or fewer', () => {
    const api = { ...mockAPI, tags: ['payments', 'stripe'] };
    renderWithProviders(<APICard api={api} />);
    expect(screen.queryByText(/^\+\d/)).not.toBeInTheDocument();
  });

  it('renders "View Details" text', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    expect(screen.getByText('View Details')).toBeInTheDocument();
  });

  it('links to the correct API detail page', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/apis/api-001');
  });

  it('renders without category or tags gracefully', () => {
    const api = { ...mockAPI, category: undefined, tags: undefined };
    renderWithProviders(<APICard api={api} />);
    expect(screen.getByText('Payments API')).toBeInTheDocument();
    expect(screen.queryByText('Finance')).not.toBeInTheDocument();
    expect(screen.queryByText(/^\+\d/)).not.toBeInTheDocument();
  });

  it('calls onMouseEnter when the card is hovered', () => {
    const onMouseEnter = vi.fn();
    renderWithProviders(<APICard api={mockAPI} onMouseEnter={onMouseEnter} />);
    fireEvent.mouseEnter(screen.getByRole('link'));
    expect(onMouseEnter).toHaveBeenCalledOnce();
  });

  it('renders a formatted updated date', () => {
    renderWithProviders(<APICard api={mockAPI} />);
    // 2026-02-01 formats to "Feb 1, 2026" in en-US locale
    expect(screen.getByText(/feb.+1.+2026/i)).toBeInTheDocument();
  });
});
