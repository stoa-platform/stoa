/**
 * Home Page - Dashboard (CAB-299, CAB-691)
 *
 * Main landing page with stats, quick actions, and recent activity.
 * Uses React Query for caching (CAB-691).
 */

import { useAuth } from '../contexts/AuthContext';
import { useDashboardStats, useDashboardActivity } from '../hooks/useDashboard';
import {
  WelcomeHeader,
  DashboardStats,
  QuickActions,
  RecentActivity,
  FeaturedAPIs,
  FeaturedAITools,
} from '../components/dashboard';

export function HomePage() {
  const { user } = useAuth();
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: activity, isLoading: activityLoading } = useDashboardActivity();

  const isLoading = statsLoading || activityLoading;

  return (
    <div className="space-y-8">
      {/* Welcome Header */}
      <WelcomeHeader user={user} />

      {/* Stats Cards */}
      <DashboardStats stats={stats ?? null} isLoading={isLoading} />

      {/* Quick Actions */}
      <QuickActions />

      {/* Featured Catalogs - API and AI Tools */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <FeaturedAPIs />
        <FeaturedAITools />
      </div>

      {/* Recent Activity */}
      <RecentActivity activity={activity ?? []} isLoading={isLoading} />
    </div>
  );
}

export default HomePage;
