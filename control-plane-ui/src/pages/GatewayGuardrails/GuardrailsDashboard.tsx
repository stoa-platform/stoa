import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { SubNav } from '../../components/SubNav';
import { observabilityTabs } from '../../components/subNavGroups';
import { TimeRangeSelector } from '@stoa/shared/components/TimeRangeSelector';
import type { TimeRange } from '@stoa/shared/components/TimeRangeSelector';
import {
  RefreshCw,
  ShieldAlert,
  Fingerprint,
  Bug,
  MessageSquareWarning,
  Zap,
  AlertTriangle,
  ExternalLink,
  Scale,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type {
  AggregatedMetrics,
  GatewayGuardrailsEvent,
  GuardrailsConfigResponse,
  GuardrailsMetricField,
  GuardrailsTimeRange,
} from '../../types';
import { guardrailCardState, type GuardrailCardUIState } from './guardrailCardState';

type FilterType = 'all' | 'pii' | 'injection' | 'content' | 'prompt' | 'rate-limit';

const GUARDRAILS_TIME_RANGES: GuardrailsTimeRange[] = ['1h', '6h', '24h', '7d'];

const ACTION_TO_FILTER: Record<string, FilterType> = {
  'pii-redacted': 'pii',
  'pii-blocked': 'pii',
  blocked: 'injection',
  'injection-blocked': 'injection',
  'content-flagged': 'content',
  'content-filter': 'content',
  'prompt-guard': 'prompt',
  'prompt-guard-blocked': 'prompt',
  'rate-limit': 'rate-limit',
  'rate-limited': 'rate-limit',
  rate_limit: 'rate-limit',
};

const FILTER_LABELS: Record<FilterType, string> = {
  all: 'All',
  pii: 'PII',
  injection: 'Injection',
  content: 'Content',
  prompt: 'Prompt',
  'rate-limit': 'Rate Limit',
};

const ACTION_BADGE: Record<string, { label: string; className: string }> = {
  'pii-redacted': {
    label: 'PII redacted',
    className: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  },
  blocked: {
    label: 'Blocked',
    className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
  'content-flagged': {
    label: 'Content flagged',
    className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  'prompt-guard': {
    label: 'Prompt guard',
    className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  },
  'rate-limit': {
    label: 'Rate limit',
    className: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  },
};

type ConfigField = keyof Pick<
  GuardrailsConfigResponse,
  | 'pii_enabled'
  | 'injection_detection_enabled'
  | 'prompt_guard_enabled'
  | 'content_filter_enabled'
  | 'rate_limit_enabled'
  | 'opa_policy_enabled'
>;

interface MetricCardConfig {
  kind: 'metric';
  icon: LucideIcon;
  title: string;
  metricField: GuardrailsMetricField;
  description: string;
  color: string;
  filter: Exclude<FilterType, 'all'>;
}

interface ConfigCardConfig {
  kind: 'config';
  icon: LucideIcon;
  title: string;
  configField: ConfigField;
  description: string;
  color: string;
}

type GuardrailCardConfig = MetricCardConfig | ConfigCardConfig;

const GUARDRAIL_CARDS: GuardrailCardConfig[] = [
  {
    kind: 'metric',
    icon: Fingerprint,
    title: 'PII Detection',
    metricField: 'pii_detections',
    description: 'Sensitive data detection and redaction outcomes',
    color: 'text-purple-600 bg-purple-50 dark:bg-purple-900/20',
    filter: 'pii',
  },
  {
    kind: 'metric',
    icon: Bug,
    title: 'Injection Blocks',
    metricField: 'injection_blocks',
    description: 'Prompt and request injection attempts blocked',
    color: 'text-red-600 bg-red-50 dark:bg-red-900/20',
    filter: 'injection',
  },
  {
    kind: 'metric',
    icon: MessageSquareWarning,
    title: 'Prompt Guard',
    metricField: 'prompt_guard_blocks',
    description: 'LLM prompt guard enforcement outcomes',
    color: 'text-amber-600 bg-amber-50 dark:bg-amber-900/20',
    filter: 'prompt',
  },
  {
    kind: 'metric',
    icon: ShieldAlert,
    title: 'Content Filter',
    metricField: 'content_filter_blocks',
    description: 'Content and payload policy filter blocks',
    color: 'text-blue-600 bg-blue-50 dark:bg-blue-900/20',
    filter: 'content',
  },
  {
    kind: 'metric',
    icon: Zap,
    title: 'Rate Limit',
    metricField: 'rate_limit_blocks',
    description: 'Requests throttled by rate-limit protection',
    color: 'text-orange-600 bg-orange-50 dark:bg-orange-900/20',
    filter: 'rate-limit',
  },
  {
    kind: 'config',
    icon: Scale,
    title: 'OPA Policy',
    configField: 'opa_policy_enabled',
    description: 'Policy evaluation enablement from runtime config',
    color: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20',
  },
];

function isGuardrailsTimeRange(range: TimeRange): range is GuardrailsTimeRange {
  return GUARDRAILS_TIME_RANGES.includes(range as GuardrailsTimeRange);
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso.slice(11, 19);
  }
}

function formatRelativeSample(iso: string): string {
  const timestampMs = new Date(iso).getTime();
  if (Number.isNaN(timestampMs)) return iso;

  const ageSeconds = Math.max(0, Math.floor((Date.now() - timestampMs) / 1000));
  if (ageSeconds < 60) return `${ageSeconds}s ago`;

  const ageMinutes = Math.floor(ageSeconds / 60);
  if (ageMinutes < 60) return `${ageMinutes} min ago`;

  const ageHours = Math.floor(ageMinutes / 60);
  if (ageHours < 24) return `${ageHours}h ago`;

  const ageDays = Math.floor(ageHours / 24);
  return `${ageDays}d ago`;
}

function isContractMetrics(metrics: AggregatedMetrics): boolean {
  const guardrails = metrics.guardrails;
  if (!guardrails) return false;

  return (
    typeof guardrails.source_healthy === 'boolean' &&
    'last_sample_at' in guardrails &&
    'metrics_age_seconds' in guardrails
  );
}

function cardStateText(state: GuardrailCardUIState): string {
  switch (state.kind) {
    case 'metrics-unavailable':
      return 'Metrics unavailable';
    case 'disabled':
      return 'Disabled';
    case 'no-sample':
      return 'No guardrail trip samples in window';
    case 'stale':
      return 'Stale metrics';
    case 'healthy':
      return `${state.count} events · last sample ${formatRelativeSample(state.lastSampleAt ?? '')}`;
  }
}

function configStatusText(
  config: GuardrailsConfigResponse | null,
  field: ConfigField,
  loading: boolean,
  unavailable: boolean
): string {
  if (loading) return 'Loading';
  if (unavailable || !config) return 'Metrics unavailable';
  return config[field] ? 'Enabled' : 'Disabled';
}

function cardTestId(title: string): string {
  return `guardrail-card-${title.toLowerCase().replace(/\s+/g, '-')}`;
}

export function GuardrailsDashboard() {
  const { isReady } = useAuth();
  const navigate = useNavigate();
  const [config, setConfig] = useState<GuardrailsConfigResponse | null>(null);
  const [metrics, setMetrics] = useState<AggregatedMetrics | null>(null);
  const [events, setEvents] = useState<GatewayGuardrailsEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [configLoading, setConfigLoading] = useState(true);
  const [configUnavailable, setConfigUnavailable] = useState(false);
  const [metricsUnavailable, setMetricsUnavailable] = useState(false);
  const [activeFilter, setActiveFilter] = useState<FilterType>('all');
  const [timeRange, setTimeRange] = useState<GuardrailsTimeRange>('1h');

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    try {
      const nextConfig = await apiService.getGuardrailsConfig();
      setConfig(nextConfig);
      setConfigUnavailable(false);
    } catch (reason) {
      console.error('Failed to load guardrails config:', reason);
      setConfig(null);
      setConfigUnavailable(true);
    } finally {
      setConfigLoading(false);
    }
  }, []);

  const loadRuntimeData = useCallback(async () => {
    setLoading(true);
    const [metricsResult, eventsResult] = await Promise.allSettled([
      apiService.getGatewayAggregatedMetrics(timeRange),
      apiService.getGuardrailsEvents(50, timeRange),
    ]);

    if (metricsResult.status === 'fulfilled' && isContractMetrics(metricsResult.value)) {
      setMetrics(metricsResult.value);
      setMetricsUnavailable(false);
    } else {
      const reason =
        metricsResult.status === 'rejected'
          ? metricsResult.reason
          : 'Guardrails metrics response missing freshness fields';
      console.error('Failed to load gateway aggregated metrics:', reason);
      setMetrics(null);
      setMetricsUnavailable(true);
    }

    if (eventsResult.status === 'fulfilled') {
      setEvents(eventsResult.value?.events ?? []);
    } else {
      console.error('Failed to load guardrails events:', eventsResult.reason);
    }

    setLoading(false);
  }, [timeRange]);

  useEffect(() => {
    if (isReady) loadConfig();
  }, [isReady, loadConfig]);

  useEffect(() => {
    if (isReady) loadRuntimeData();
  }, [isReady, loadRuntimeData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadRuntimeData, 30_000);
    return () => clearInterval(interval);
  }, [isReady, loadRuntimeData]);

  const handleRefresh = () => {
    void Promise.all([loadConfig(), loadRuntimeData()]);
  };

  const filteredEvents =
    activeFilter === 'all'
      ? events
      : events.filter((event) => ACTION_TO_FILTER[event.action] === activeFilter);

  const emptyEventsText =
    activeFilter === 'rate-limit'
      ? 'No rate-limit events'
      : events.length === 0
        ? `No guardrail events in the selected ${timeRange} window`
        : `No ${FILTER_LABELS[activeFilter].toLowerCase()} events found`;

  return (
    <div className="space-y-6">
      <SubNav tabs={observabilityTabs} />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
            Security & Guardrails
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring
          </p>
        </div>
        <div className="flex items-center gap-3">
          <TimeRangeSelector
            value={timeRange}
            ranges={GUARDRAILS_TIME_RANGES}
            onChange={(range) => {
              if (isGuardrailsTimeRange(range)) setTimeRange(range);
            }}
          />
          <button
            onClick={handleRefresh}
            disabled={loading || configLoading}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${loading || configLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {(configUnavailable || metricsUnavailable) && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-4 text-red-700 dark:text-red-400">
          <AlertTriangle className="inline h-4 w-4 mr-2" />
          Metrics unavailable
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {GUARDRAIL_CARDS.map((card) => {
          const Icon = card.icon;
          const state =
            card.kind === 'metric'
              ? guardrailCardState(config, metrics, card.metricField, { metricsUnavailable })
              : null;
          const statusText =
            card.kind === 'metric'
              ? cardStateText(state as GuardrailCardUIState)
              : configStatusText(config, card.configField, configLoading, configUnavailable);
          const isDisabled =
            statusText === 'Disabled' ||
            statusText === 'Metrics unavailable' ||
            statusText === 'No guardrail trip samples in window';
          const isFilterable =
            card.kind === 'metric' &&
            !isDisabled &&
            state?.kind !== 'stale' &&
            Boolean(card.filter);
          const isActive = card.kind === 'metric' && activeFilter === card.filter;
          const className = `rounded-lg border p-5 text-left transition-all ${card.color} ${
            isActive
              ? 'ring-2 ring-current border-current'
              : 'border-neutral-200 dark:border-neutral-700'
          } ${
            isFilterable
              ? 'cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-current'
              : 'cursor-default'
          } ${isDisabled ? 'opacity-75' : ''}`;
          const content = (
            <>
              <div className="flex items-center gap-2 mb-3">
                <Icon className="h-5 w-5" />
                <span className="text-sm font-semibold">{card.title}</span>
              </div>
              {loading && card.kind === 'metric' && !metrics && !metricsUnavailable ? (
                <div className="h-6 w-32 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
              ) : (
                <p className="text-sm font-semibold">{statusText}</p>
              )}
              <p className="text-xs mt-2 opacity-75">{card.description}</p>
            </>
          );

          if (!isFilterable || card.kind !== 'metric') {
            return (
              <div key={card.title} className={className} data-testid={cardTestId(card.title)}>
                {content}
              </div>
            );
          }

          return (
            <button
              key={card.title}
              onClick={() =>
                setActiveFilter((prev) => (prev === card.filter ? 'all' : card.filter))
              }
              className={className}
              data-testid={cardTestId(card.title)}
            >
              {content}
            </button>
          );
        })}
      </div>

      <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Recent Events
            {activeFilter !== 'all' && (
              <span className="ml-2 text-sm font-normal text-neutral-500">
                — {FILTER_LABELS[activeFilter]}
                <button
                  onClick={() => setActiveFilter('all')}
                  className="ml-1 text-blue-600 hover:underline"
                >
                  clear
                </button>
              </span>
            )}
          </h2>
          <span className="text-xs text-neutral-400">{filteredEvents.length} events</span>
        </div>
        {filteredEvents.length === 0 ? (
          <div className="p-8 text-center text-neutral-400 text-sm">{emptyEventsText}</div>
        ) : (
          <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {filteredEvents.map((event) => {
              const badge = ACTION_BADGE[event.action] ?? {
                label: event.action,
                className:
                  'bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300',
              };
              return (
                <button
                  key={event.span_id}
                  onClick={() => navigate(`/observability/live-calls/trace/${event.trace_id}`)}
                  className="flex items-center gap-4 w-full px-4 py-3 text-left text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors"
                >
                  <span className="text-neutral-400 font-mono text-xs w-20 shrink-0">
                    {formatTimestamp(event.timestamp)}
                  </span>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${badge.className}`}
                  >
                    {badge.label}
                  </span>
                  <span className="font-mono text-neutral-700 dark:text-neutral-300 truncate">
                    {event.tool}
                  </span>
                  {event.reason && (
                    <span className="text-neutral-400 text-xs truncate hidden sm:inline">
                      {event.reason}
                    </span>
                  )}
                  <ExternalLink className="h-3.5 w-3.5 text-neutral-300 ml-auto shrink-0" />
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700">
        <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
            Guardrail Configuration
          </h2>
          {config && !configUnavailable && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              Source: {config.source} · Updated {formatRelativeSample(config.updated_at)}
            </p>
          )}
        </div>
        <div className="p-4 space-y-3">
          <ConfigRow
            label="PII Detection"
            status={configStatusText(config, 'pii_enabled', configLoading, configUnavailable)}
            testId="config-pii-detection"
          />
          <ConfigRow
            label="Injection Detection"
            status={configStatusText(
              config,
              'injection_detection_enabled',
              configLoading,
              configUnavailable
            )}
            testId="config-injection-detection"
          />
          <ConfigRow
            label="Prompt Guard"
            status={configStatusText(
              config,
              'prompt_guard_enabled',
              configLoading,
              configUnavailable
            )}
            testId="config-prompt-guard"
          />
          <ConfigRow
            label="Content Filter"
            status={configStatusText(
              config,
              'content_filter_enabled',
              configLoading,
              configUnavailable
            )}
            testId="config-content-filter"
          />
          <ConfigRow
            label="Rate Limit"
            status={configStatusText(
              config,
              'rate_limit_enabled',
              configLoading,
              configUnavailable
            )}
            testId="config-rate-limit"
          />
          <ConfigRow
            label="OPA Policy"
            status={configStatusText(
              config,
              'opa_policy_enabled',
              configLoading,
              configUnavailable
            )}
            testId="config-opa-policy"
          />
        </div>
      </div>
    </div>
  );
}

function ConfigRow({ label, status, testId }: { label: string; status: string; testId: string }) {
  const statusClass =
    status === 'Enabled'
      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
      : status === 'Disabled'
        ? 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400'
        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';

  return (
    <div
      className="flex items-center justify-between py-2 border-b border-neutral-100 dark:border-neutral-800 last:border-0"
      data-testid={testId}
    >
      <span className="text-sm text-neutral-700 dark:text-neutral-300">{label}</span>
      <span className={`text-xs font-medium px-2 py-1 rounded-full ${statusClass}`}>{status}</span>
    </div>
  );
}
