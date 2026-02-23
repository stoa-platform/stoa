import { useQuery } from '@tanstack/react-query';
import { Activity, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';

function formatNumber(n: number): string {
  return n.toLocaleString();
}

function usageColor(percent: number): {
  ring: string;
  text: string;
  stroke: string;
} {
  if (percent >= 80)
    return {
      ring: 'text-red-500 dark:text-red-400',
      text: 'text-red-600 dark:text-red-400',
      stroke: '#ef4444',
    };
  if (percent >= 60)
    return {
      ring: 'text-amber-500 dark:text-amber-400',
      text: 'text-amber-600 dark:text-amber-400',
      stroke: '#f59e0b',
    };
  return {
    ring: 'text-emerald-500 dark:text-emerald-400',
    text: 'text-emerald-600 dark:text-emerald-400',
    stroke: '#10b981',
  };
}

export function TokenUsageWidget() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const tenantId = user?.tenant_id;

  const {
    data: budget,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['chat-budget', tenantId],
    queryFn: () => apiService.getChatBudgetStatus(tenantId!),
    enabled: !!tenantId,
    staleTime: 60_000,
  });

  if (!tenantId) return null;

  if (isLoading) {
    return (
      <div
        data-testid="token-usage-loading"
        className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6 animate-pulse"
      >
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-neutral-200 dark:bg-neutral-700" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-32 bg-neutral-200 dark:bg-neutral-700 rounded" />
            <div className="h-3 w-48 bg-neutral-200 dark:bg-neutral-700 rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (isError || !budget) {
    return (
      <div
        data-testid="token-usage-error"
        className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6"
      >
        <div className="flex items-center gap-3 text-neutral-400 dark:text-neutral-500">
          <Activity className="w-5 h-5" />
          <span className="text-sm">{t('tokenUsage.unavailable', 'Token usage unavailable')}</span>
        </div>
      </div>
    );
  }

  const percent = Math.min(budget.usage_percent, 100);
  const colors = usageColor(percent);

  // SVG circular progress
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (percent / 100) * circumference;

  return (
    <div
      data-testid="token-usage-widget"
      className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6"
    >
      <div className="flex items-center gap-6">
        {/* Circular progress */}
        <div className="relative flex-shrink-0 w-16 h-16">
          <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
            <circle
              cx="32"
              cy="32"
              r={radius}
              fill="none"
              stroke="currentColor"
              strokeWidth="6"
              className="text-neutral-200 dark:text-neutral-700"
            />
            <circle
              cx="32"
              cy="32"
              r={radius}
              fill="none"
              stroke={colors.stroke}
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              data-testid="progress-ring"
            />
          </svg>
          <span
            className={`absolute inset-0 flex items-center justify-center text-xs font-bold ${colors.text}`}
          >
            {Math.round(percent)}%
          </span>
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-neutral-400" />
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
              {t('tokenUsage.title', 'Token Budget')}
            </h3>
          </div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            {t('tokenUsage.todayUsage', '{{used}} / {{budget}} tokens today', {
              used: formatNumber(budget.user_tokens_today),
              budget: formatNumber(budget.daily_budget),
            })}
          </p>
          <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">
            {t('tokenUsage.remaining', '{{remaining}} remaining', {
              remaining: formatNumber(budget.remaining),
            })}
          </p>

          {budget.budget_exceeded && (
            <div
              data-testid="budget-exceeded-warning"
              className="flex items-center gap-1.5 mt-2 text-xs text-red-600 dark:text-red-400"
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>{t('tokenUsage.exceeded', 'Daily budget exceeded')}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
