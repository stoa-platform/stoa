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
import { PermissionGate } from '../components/common/PermissionGate';

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
        <PermissionGate scope="stoa:catalog:read">
          <FeaturedAPIs />
        </PermissionGate>
        <PermissionGate scope="stoa:tools:read">
          <FeaturedAITools />
        </PermissionGate>
      </div>

      {/* Recent Activity */}
      <PermissionGate scope="stoa:subscriptions:read">
        <RecentActivity activity={activity ?? []} isLoading={isLoading} />
      </PermissionGate>
    </div>
  );
}

export default HomePage;
