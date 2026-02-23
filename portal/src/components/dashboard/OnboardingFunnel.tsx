/**
 * OnboardingFunnel — Horizontal bar chart with conversion rates + TTFTC stats (CAB-1325 Phase 3)
 *
 * Admin-only component showing onboarding funnel analytics.
 */

import { Users, Clock, AlertTriangle } from 'lucide-react';
import { useOnboardingFunnel, useStalledUsers } from '../../hooks/useOnboardingAnalytics';

const STAGE_LABELS: Record<string, string> = {
  registered: 'Registered',
  choose_use_case: 'Chose Use Case',
  create_app: 'Created App',
  subscribe_api: 'Subscribed to API',
  first_call: 'First Tool Call',
};

function formatSeconds(seconds: number | null): string {
  if (seconds === null) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

export function OnboardingFunnel() {
  const { data: funnel, isLoading, error } = useOnboardingFunnel();
  const { data: stalled } = useStalledUsers();

  if (isLoading) {
    return (
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 w-48 bg-neutral-200 dark:bg-neutral-700 rounded" />
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-8 bg-neutral-200 dark:bg-neutral-700 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !funnel) {
    return null;
  }

  const maxCount = Math.max(...funnel.stages.map((s) => s.count), 1);
  const stalledCount = stalled?.length ?? 0;

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-primary-600 dark:text-primary-400" />
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            Onboarding Funnel
          </h3>
        </div>
        <span className="text-sm text-neutral-500 dark:text-neutral-400">
          {funnel.total_started} users started
        </span>
      </div>

      {/* Funnel Bars */}
      <div className="space-y-3">
        {funnel.stages.map((stage) => {
          const pct = maxCount > 0 ? (stage.count / maxCount) * 100 : 0;
          const rate =
            stage.conversion_rate !== null ? (stage.conversion_rate * 100).toFixed(0) : null;

          return (
            <div key={stage.stage} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="text-neutral-700 dark:text-neutral-300">
                  {STAGE_LABELS[stage.stage] ?? stage.stage}
                </span>
                <span className="text-neutral-500 dark:text-neutral-400">
                  {stage.count}
                  {rate !== null && (
                    <span className="ml-1 text-xs text-neutral-400 dark:text-neutral-500">({rate}%)</span>
                  )}
                </span>
              </div>
              <div className="h-6 bg-neutral-100 dark:bg-neutral-700 rounded-md overflow-hidden">
                <div
                  className="h-full bg-primary-500 dark:bg-primary-400 rounded-md transition-all duration-500"
                  style={{ width: `${Math.max(pct, 2)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* TTFTC Stats */}
      <div className="grid grid-cols-3 gap-4 pt-4 border-t border-neutral-200 dark:border-neutral-700">
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <Clock className="h-4 w-4 text-neutral-400" />
            <span className="text-xs text-neutral-500 dark:text-neutral-400">Avg TTFTC</span>
          </div>
          <span className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {formatSeconds(funnel.avg_ttftc_seconds)}
          </span>
        </div>
        <div className="text-center">
          <span className="text-xs text-neutral-500 dark:text-neutral-400">P50</span>
          <p className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {formatSeconds(funnel.p50_ttftc_seconds)}
          </p>
        </div>
        <div className="text-center">
          <span className="text-xs text-neutral-500 dark:text-neutral-400">P90</span>
          <p className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {formatSeconds(funnel.p90_ttftc_seconds)}
          </p>
        </div>
      </div>

      {/* Stalled Users Alert */}
      {stalledCount > 0 && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg">
          <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0" />
          <span className="text-sm text-amber-800 dark:text-amber-200">
            {stalledCount} user{stalledCount !== 1 ? 's' : ''} stalled in onboarding (&gt;24h)
          </span>
        </div>
      )}
    </div>
  );
}

export default OnboardingFunnel;
