import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { RecentActivity } from '../RecentActivity';
import { renderWithProviders, mockDashboardActivity } from '../../../test/helpers';
import type { RecentActivityItem } from '../../../types';

describe('RecentActivity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Recent Activity heading', () => {
    renderWithProviders(<RecentActivity activity={[]} />);

    expect(screen.getByText('Recent Activity')).toBeInTheDocument();
  });

  it('renders View all link', () => {
    renderWithProviders(<RecentActivity activity={[]} />);

    expect(screen.getByText('View all')).toBeInTheDocument();
  });

  it('renders empty state when no activity', () => {
    renderWithProviders(<RecentActivity activity={[]} />);

    expect(screen.getByText('No recent activity')).toBeInTheDocument();
  });

  it('renders loading skeleton when isLoading is true', () => {
    const { container } = renderWithProviders(<RecentActivity activity={[]} isLoading={true} />);

    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('renders activity items', () => {
    const activity = mockDashboardActivity() as RecentActivityItem[];
    renderWithProviders(<RecentActivity activity={activity} />);

    expect(screen.getByText('New subscription')).toBeInTheDocument();
    expect(screen.getByText('API Call')).toBeInTheDocument();
  });

  it('renders activity descriptions', () => {
    const activity = mockDashboardActivity() as RecentActivityItem[];
    renderWithProviders(<RecentActivity activity={activity} />);

    expect(screen.getByText('Subscribed to Payment API')).toBeInTheDocument();
  });

  it('renders timestamps for activity items', () => {
    // Use recent timestamps so formatRelativeTime returns "Xh ago" or "Xm ago"
    const now = new Date();
    const twoHoursAgo = new Date(now.getTime() - 2 * 3600000).toISOString();
    const thirtyMinAgo = new Date(now.getTime() - 30 * 60000).toISOString();
    const recentActivity: RecentActivityItem[] = [
      {
        id: 'a1',
        type: 'subscription.created',
        title: 'New subscription',
        description: 'Subscribed to Payment API',
        tool_id: 'tool-1',
        timestamp: twoHoursAgo,
      },
      {
        id: 'a2',
        type: 'api.call',
        title: 'API Call',
        description: 'Called list-apis',
        tool_id: 'tool-1',
        timestamp: thirtyMinAgo,
      },
    ];
    renderWithProviders(<RecentActivity activity={recentActivity} />);

    const timeElements = screen.getAllByText(/ago/);
    expect(timeElements.length).toBeGreaterThan(0);
  });

  it('does not show empty state when activity exists', () => {
    const activity = mockDashboardActivity() as RecentActivityItem[];
    renderWithProviders(<RecentActivity activity={activity} />);

    expect(screen.queryByText('No recent activity')).not.toBeInTheDocument();
  });
});
