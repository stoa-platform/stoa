/**
 * Rate Limits Dashboard (CAB-1470)
 */

import { Gauge, AlertTriangle } from 'lucide-react';
import { useRateLimits } from '../../hooks/useRateLimits';
import { useAuth } from '../../contexts/AuthContext';
import type { RateLimitStatus } from '../../types';

function UsageBar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
  const color = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500';

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-neutral-600 dark:text-neutral-300">
          {used.toLocaleString()} / {limit.toLocaleString()}
        </span>
        <span className="text-neutral-400">{pct.toFixed(0)}%</span>
      </div>
      <div className="h-2 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function RateLimitCard({ rl }: { rl: RateLimitStatus }) {
  const pct = rl.limit > 0 ? (rl.used / rl.limit) * 100 : 0;

  return (
    <div className="p-4 bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-medium text-neutral-900 dark:text-white">{rl.api_name}</h3>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {rl.plan_name} &middot; per {rl.period}
          </p>
        </div>
        {pct >= 90 && <AlertTriangle className="w-5 h-5 text-red-500" />}
      </div>
      <UsageBar used={rl.used} limit={rl.limit} />
      <div className="flex justify-between mt-2 text-xs text-neutral-400">
        <span>{rl.remaining.toLocaleString()} remaining</span>
        <span>Resets {new Date(rl.reset_at).toLocaleTimeString()}</span>
      </div>
    </div>
  );
}

export function RateLimitsPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { data, isLoading } = useRateLimits();

  if (authLoading || !isAuthenticated) {
    return null;
  }

  const rateLimits = data?.rate_limits ?? [];

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Gauge className="w-6 h-6 text-neutral-700 dark:text-neutral-200" />
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Rate Limits</h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Monitor your API usage quotas
            </p>
          </div>
        </div>

        {/* Grid */}
        {isLoading ? (
          <div className="text-center py-8 text-neutral-400">Loading rate limits...</div>
        ) : rateLimits.length === 0 ? (
          <div className="text-center py-16">
            <Gauge className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
            <h2 className="text-lg font-medium text-neutral-600 dark:text-neutral-300">
              No active rate limits
            </h2>
            <p className="text-sm text-neutral-400 mt-1">
              Subscribe to APIs to see your usage quotas here
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {rateLimits.map((rl) => (
              <RateLimitCard key={`${rl.api_id}-${rl.subscription_id}`} rl={rl} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default RateLimitsPage;
