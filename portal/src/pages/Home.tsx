/**
 * Home Page - Dashboard (CAB-299, CAB-691, CAB-1323)
 *
 * Main landing page with stats, quick actions, and recent activity.
 * Uses React Query for caching (CAB-691).
 * RBAC widget visibility: scope-gated sections (CAB-1323 P2).
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
  GettingStartedChecklist,
} from '../components/dashboard';
import { PermissionGate } from '../components/common/PermissionGate';
import { GrafanaDashboard } from '../components/usage/GrafanaDashboard';
import { TenantBadge } from '../components/layout/TenantBadge';
import { config } from '../config';

export function HomePage() {
  const { user } = useAuth();
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: activity, isLoading: activityLoading } = useDashboardActivity();

  const isLoading = statsLoading || activityLoading;

  return (
    <div className="space-y-8">
      {/* Welcome Header + Tenant Context */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <WelcomeHeader user={user} />
        <TenantBadge />
      </div>

      {/* Onboarding Checklist — shown until complete (CAB-1325) */}
      <GettingStartedChecklist />

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

      {/* Analytics Dashboard - metrics scope only */}
      <PermissionGate scope="stoa:metrics:read">
        <GrafanaDashboard url={config.grafana.url} title="Usage Analytics" />
      </PermissionGate>
    </div>
  );
}

export default HomePage;
