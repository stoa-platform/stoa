// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Home Page - Dashboard (CAB-299)
 *
 * Main landing page with stats, quick actions, and recent activity.
 */

import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { dashboardService } from '../services/dashboard';
import {
  WelcomeHeader,
  DashboardStats,
  QuickActions,
  RecentActivity,
  FeaturedAPIs,
  FeaturedAITools,
} from '../components/dashboard';
import type { DashboardStats as DashboardStatsType, RecentActivityItem } from '../types';

export function HomePage() {
  const { user, isAuthenticated, accessToken } = useAuth();
  const [stats, setStats] = useState<DashboardStatsType | null>(null);
  const [activity, setActivity] = useState<RecentActivityItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Wait for both authentication AND token to be available
    if (!isAuthenticated || !accessToken) return;

    async function loadDashboard() {
      setIsLoading(true);
      try {
        const data = await dashboardService.getDashboard();
        setStats(data.stats);
        setActivity(data.recent_activity);
      } catch (error) {
        console.error('Failed to load dashboard:', error);
      } finally {
        setIsLoading(false);
      }
    }

    loadDashboard();
  }, [isAuthenticated, accessToken]);

  return (
    <div className="space-y-8">
      {/* Welcome Header */}
      <WelcomeHeader user={user} />

      {/* Stats Cards */}
      <DashboardStats stats={stats} isLoading={isLoading} />

      {/* Quick Actions */}
      <QuickActions />

      {/* Featured Catalogs - API and AI Tools */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <FeaturedAPIs />
        <FeaturedAITools />
      </div>

      {/* Recent Activity */}
      <RecentActivity activity={activity} isLoading={isLoading} />
    </div>
  );
}

export default HomePage;
