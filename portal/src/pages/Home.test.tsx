/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for Home page (Dashboard — CAB-299)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HomePage } from './Home';

// Mock AuthContext
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'user-1', name: 'Test User', roles: ['tenant-admin'] },
    isAuthenticated: true,
    isReady: true,
  }),
}));

// Mock dashboard hooks
const mockStatsData = {
  tools_available: 10,
  active_subscriptions: 5,
  api_calls_this_week: 1234,
};

const mockActivityData = [
  { id: 'a1', type: 'api.call', title: 'API Call 1', timestamp: '2026-02-07T10:00:00Z' },
];

vi.mock('../hooks/useDashboard', () => ({
  useDashboardStats: () => ({
    data: mockStatsData,
    isLoading: false,
  }),
  useDashboardActivity: () => ({
    data: mockActivityData,
    isLoading: false,
  }),
}));

// Mock dashboard components
vi.mock('../components/dashboard', () => ({
  WelcomeHeader: ({ user }: { user: any }) => (
    <div data-testid="welcome-header">{user?.name}</div>
  ),
  DashboardStats: ({ isLoading }: { stats: any; isLoading: boolean }) => (
    <div data-testid="dashboard-stats">{isLoading ? 'Loading' : 'Stats loaded'}</div>
  ),
  QuickActions: () => <div data-testid="quick-actions">Quick Actions</div>,
  RecentActivity: ({ activity }: { activity: any[] }) => (
    <div data-testid="recent-activity">{activity.length} items</div>
  ),
  FeaturedAPIs: () => <div data-testid="featured-apis">Featured APIs</div>,
  FeaturedAITools: () => <div data-testid="featured-ai-tools">Featured AI Tools</div>,
}));

describe('HomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render all dashboard sections', () => {
    render(<HomePage />);

    expect(screen.getByTestId('welcome-header')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-stats')).toBeInTheDocument();
    expect(screen.getByTestId('quick-actions')).toBeInTheDocument();
    expect(screen.getByTestId('featured-apis')).toBeInTheDocument();
    expect(screen.getByTestId('featured-ai-tools')).toBeInTheDocument();
    expect(screen.getByTestId('recent-activity')).toBeInTheDocument();
  });

  it('should pass user to WelcomeHeader', () => {
    render(<HomePage />);

    expect(screen.getByTestId('welcome-header')).toHaveTextContent('Test User');
  });

  it('should pass stats to DashboardStats', () => {
    render(<HomePage />);

    expect(screen.getByTestId('dashboard-stats')).toHaveTextContent('Stats loaded');
  });

  it('should pass activity to RecentActivity', () => {
    render(<HomePage />);

    expect(screen.getByTestId('recent-activity')).toHaveTextContent('1 items');
  });
});
