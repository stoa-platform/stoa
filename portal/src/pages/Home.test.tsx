/**
 * Tests for Home page (Dashboard — CAB-1133)
 *
 * Page-level functional tests covering all personas (halliday, parzival, art3mis, aech).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { HomePage } from './Home';
import {
  renderWithProviders,
  createAuthMock,
  mockDashboardStats,
  mockDashboardActivity,
} from '../test/helpers';

// Mock dashboard hooks
const mockStatsData = mockDashboardStats();
const mockActivityData = mockDashboardActivity();

const mockUseDashboardStats = vi.fn();
const mockUseDashboardActivity = vi.fn();

vi.mock('../hooks/useDashboard', () => ({
  useDashboardStats: () => mockUseDashboardStats(),
  useDashboardActivity: () => mockUseDashboardActivity(),
}));

// Mock AuthContext with dynamic return
const mockUseAuth = vi.fn();
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock dashboard components as simple stubs
vi.mock('../components/dashboard', () => ({
  WelcomeHeader: ({ user }: { user: { name: string } | null }) => (
    <div data-testid="welcome-header">{user?.name || 'Guest'}</div>
  ),
  DashboardStats: ({
    stats,
    isLoading,
  }: {
    stats: Record<string, unknown> | null;
    isLoading: boolean;
  }) => (
    <div data-testid="dashboard-stats">
      {isLoading ? 'Loading stats' : stats ? 'Stats loaded' : 'No stats'}
    </div>
  ),
  QuickActions: () => <div data-testid="quick-actions">Quick Actions</div>,
  RecentActivity: ({ activity, isLoading }: { activity: unknown[]; isLoading: boolean }) => (
    <div data-testid="recent-activity">
      {isLoading ? 'Loading activity' : `${activity.length} items`}
    </div>
  ),
  FeaturedAPIs: () => <div data-testid="featured-apis">Featured APIs</div>,
  FeaturedAITools: () => <div data-testid="featured-ai-tools">Featured AI Tools</div>,
  OnboardingFunnel: () => <div data-testid="onboarding-funnel">Onboarding Funnel</div>,
}));

describe('HomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDashboardStats.mockReturnValue({
      data: mockStatsData,
      isLoading: false,
    });
    mockUseDashboardActivity.mockReturnValue({
      data: mockActivityData,
      isLoading: false,
    });
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  describe('Component Structure', () => {
    it('should render all 6 dashboard sections', () => {
      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('welcome-header')).toBeInTheDocument();
      expect(screen.getByTestId('dashboard-stats')).toBeInTheDocument();
      expect(screen.getByTestId('quick-actions')).toBeInTheDocument();
      expect(screen.getByTestId('featured-apis')).toBeInTheDocument();
      expect(screen.getByTestId('featured-ai-tools')).toBeInTheDocument();
      expect(screen.getByTestId('recent-activity')).toBeInTheDocument();
    });

    it('should pass user to WelcomeHeader', () => {
      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('welcome-header')).toHaveTextContent('Wade Watts');
    });

    it('should pass stats data to DashboardStats when loaded', () => {
      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('dashboard-stats')).toHaveTextContent('Stats loaded');
    });

    it('should pass activity data to RecentActivity', () => {
      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('recent-activity')).toHaveTextContent('2 items');
    });
  });

  describe('Loading State', () => {
    it('should show loading when stats are loading', () => {
      mockUseDashboardStats.mockReturnValue({
        data: undefined,
        isLoading: true,
      });

      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('dashboard-stats')).toHaveTextContent('Loading stats');
      expect(screen.getByTestId('recent-activity')).toHaveTextContent('Loading activity');
    });

    it('should show loading when activity is loading', () => {
      mockUseDashboardActivity.mockReturnValue({
        data: undefined,
        isLoading: true,
      });

      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('dashboard-stats')).toHaveTextContent('Loading stats');
      expect(screen.getByTestId('recent-activity')).toHaveTextContent('Loading activity');
    });

    it('should pass isLoading=true when either stats or activity loading', () => {
      mockUseDashboardStats.mockReturnValue({
        data: mockStatsData,
        isLoading: true,
      });
      mockUseDashboardActivity.mockReturnValue({
        data: mockActivityData,
        isLoading: false,
      });

      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('dashboard-stats')).toHaveTextContent('Loading stats');
    });
  });

  describe('Persona-based Tests', () => {
    it('should render for cpi-admin (James Halliday)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));

      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('welcome-header')).toHaveTextContent('James Halliday');
    });

    it('should render for tenant-admin (Wade Watts)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));

      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('welcome-header')).toHaveTextContent('Wade Watts');
    });

    it('should render for devops (Samantha Cook)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('devops'));

      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('welcome-header')).toHaveTextContent('Samantha Cook');
    });

    it('should render for viewer (Helen Harris)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('viewer'));

      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('welcome-header')).toHaveTextContent('Helen Harris');
    });
  });
});
