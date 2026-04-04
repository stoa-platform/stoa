import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { SubNav } from '../../components/SubNav';
import { gatewayTabs } from '../../components/subNavGroups';
import {
  RefreshCw,
  ShieldAlert,
  Fingerprint,
  Bug,
  MessageSquareWarning,
  Zap,
  AlertTriangle,
} from 'lucide-react';

interface GuardrailStats {
  pii_detections: number;
  injection_blocks: number;
  content_filters: number;
  prompt_guard_flags: number;
  rate_limit_enforcements: number;
}

export function GuardrailsDashboard() {
  const { isReady } = useAuth();
  const [stats, setStats] = useState<GuardrailStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      // Guardrail metrics come from gateway /metrics — fetch via CP API aggregation
      const metrics = await apiService.getGatewayAggregatedMetrics().catch(() => null);

      // Extract guardrail stats from aggregated metrics (if available)
      setStats({
        pii_detections: metrics?.guardrails?.pii_detections || 0,
        injection_blocks: metrics?.guardrails?.injection_blocks || 0,
        content_filters: metrics?.guardrails?.content_filters || 0,
        prompt_guard_flags: metrics?.guardrails?.prompt_guard_flags || 0,
        rate_limit_enforcements: metrics?.rate_limiting?.enforcements || 0,
      });
      setError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load guardrail metrics';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, 30_000);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  const guardrailCards = [
    {
      icon: Fingerprint,
      title: 'PII Detection',
      value: stats?.pii_detections ?? 0,
      description: 'SSN, credit card, phone, email patterns blocked',
      color: 'text-purple-600 bg-purple-50 dark:bg-purple-900/20',
    },
    {
      icon: Bug,
      title: 'Injection Blocks',
      value: stats?.injection_blocks ?? 0,
      description: 'SQL, XPath, command injection attempts blocked',
      color: 'text-red-600 bg-red-50 dark:bg-red-900/20',
    },
    {
      icon: MessageSquareWarning,
      title: 'Prompt Guard',
      value: stats?.prompt_guard_flags ?? 0,
      description: 'LLM prompt injection attempts flagged',
      color: 'text-amber-600 bg-amber-50 dark:bg-amber-900/20',
    },
    {
      icon: ShieldAlert,
      title: 'Content Filters',
      value: stats?.content_filters ?? 0,
      description: 'MIME type and body size violations',
      color: 'text-blue-600 bg-blue-50 dark:bg-blue-900/20',
    },
    {
      icon: Zap,
      title: 'Rate Limit',
      value: stats?.rate_limit_enforcements ?? 0,
      description: 'Requests throttled by token bucket',
      color: 'text-orange-600 bg-orange-50 dark:bg-orange-900/20',
    },
  ];

  return (
    <div className="space-y-6">
      <SubNav tabs={gatewayTabs} />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            Gateway Guardrails
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Request/response protection — PII, injection, prompt guard, rate limiting
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-4 text-red-700 dark:text-red-400">
          <AlertTriangle className="inline h-4 w-4 mr-2" />
          {error}
        </div>
      )}

      {/* Guardrail Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {guardrailCards.map((card) => (
          <div
            key={card.title}
            className={`rounded-lg border border-neutral-200 dark:border-neutral-700 p-5 ${card.color}`}
          >
            <div className="flex items-center gap-2 mb-3">
              <card.icon className="h-5 w-5" />
              <span className="text-sm font-semibold">{card.title}</span>
            </div>
            {loading ? (
              <div className="h-8 w-16 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
            ) : (
              <p className="text-3xl font-bold">{card.value}</p>
            )}
            <p className="text-xs mt-2 opacity-75">{card.description}</p>
          </div>
        ))}
      </div>

      {/* Feature Status */}
      <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Guardrail Configuration
          </h2>
        </div>
        <div className="p-4 space-y-3">
          <ConfigRow label="PII Detection" envVar="GUARDRAILS_PII_ENABLED" />
          <ConfigRow label="Injection Protection" envVar="GUARDRAILS_INJECTION_ENABLED" />
          <ConfigRow label="Content Filter" envVar="GUARDRAILS_CONTENT_FILTER_ENABLED" />
          <ConfigRow label="Prompt Guard" envVar="PROMPT_GUARD_ENABLED" />
          <ConfigRow label="OPA Policy Engine" envVar="POLICY_ENABLED" />
        </div>
      </div>
    </div>
  );
}

function ConfigRow({ label, envVar }: { label: string; envVar: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-neutral-100 dark:border-neutral-800 last:border-0">
      <span className="text-sm text-neutral-700 dark:text-neutral-300">{label}</span>
      <code className="text-xs text-neutral-500 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-800 px-2 py-1 rounded">
        {envVar}
      </code>
    </div>
  );
}
