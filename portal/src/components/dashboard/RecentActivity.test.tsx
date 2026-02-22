/**
 * Tests for RecentActivity (CAB-1390)
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { RecentActivity } from './RecentActivity';
import { renderWithProviders, mockDashboardActivity } from '../../test/helpers';

describe('RecentActivity', () => {
  it('shows loading skeletons when isLoading is true', () => {
    const { container } = renderWithProviders(<RecentActivity activity={[]} isLoading={true} />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows empty state when activity is empty', () => {
    renderWithProviders(<RecentActivity activity={[]} />);
    expect(screen.getByText('No recent activity')).toBeInTheDocument();
  });

  it('shows CTA text when activity is empty', () => {
    renderWithProviders(<RecentActivity activity={[]} />);
    expect(screen.getByText(/subscribe to tools/i)).toBeInTheDocument();
  });

  it('renders activity items when data is available', () => {
    const activity = mockDashboardActivity();
    renderWithProviders(<RecentActivity activity={activity as never} />);
    expect(screen.getByText('New subscription')).toBeInTheDocument();
  });

  it('renders activity item description', () => {
    const activity = mockDashboardActivity();
    renderWithProviders(<RecentActivity activity={activity as never} />);
    expect(screen.getByText('Subscribed to Payment API')).toBeInTheDocument();
  });

  it('renders a relative timestamp for each activity item', () => {
    const activity = mockDashboardActivity();
    renderWithProviders(<RecentActivity activity={activity as never} />);
    // Timestamps are formatted as "Xd ago" / "Xh ago" / date
    const timeElements = screen.getAllByText(/ago|just now|\d{4}/i);
    expect(timeElements.length).toBeGreaterThan(0);
  });
});
