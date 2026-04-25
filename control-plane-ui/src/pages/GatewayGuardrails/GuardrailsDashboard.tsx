import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
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
  ExternalLink,
} from 'lucide-react';

interface GuardrailStats {
  pii_detections: number;
  injection_blocks: number;
  content_filters: number;
  prompt_guard_flags: number;
  rate_limit_enforcements: number;
  by_tool: Record<string, number>;
  by_category: Record<string, number>;
}

interface GuardrailEvent {
  timestamp: string;
  trace_id: string;
  span_id: string;
  tool: string;
  action: string;
  reason: string;
}

type FilterType = 'all' | 'pii' | 'injection' | 'content' | 'prompt';

const ACTION_TO_FILTER: Record<string, FilterType> = {
  'pii-redacted': 'pii',
  'pii-blocked': 'pii',
  blocked: 'injection',
  'content-flagged': 'content',
  'prompt-guard': 'prompt',
};

const FILTER_LABELS: Record<FilterType, string> = {
  all: 'All',
  pii: 'PII',
  injection: 'Injection',
  content: 'Content',
  prompt: 'Prompt',
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
};

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso.slice(11, 19);
  }
}

export function GuardrailsDashboard() {
  const { isReady } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState<GuardrailStats | null>(null);
  const [events, setEvents] = useState<GuardrailEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterType>('all');

  const loadData = useCallback(async () => {
    setLoading(true);
    // P1-1: allSettled — each endpoint independent, partial failure leaves
    // the other slice's prior state intact.
    const [metricsResult, eventsResult] = await Promise.allSettled([
      apiService.getGatewayAggregatedMetrics(),
      apiService.getGuardrailsEvents(50),
    ]);

    if (metricsResult.status === 'fulfilled') {
      const metrics = metricsResult.value;
      setStats({
        pii_detections: metrics?.guardrails?.pii_detections || 0,
        injection_blocks: metrics?.guardrails?.injection_blocks || 0,
        content_filters: metrics?.guardrails?.content_filters || 0,
        prompt_guard_flags: metrics?.guardrails?.prompt_guard_flags || 0,
        rate_limit_enforcements: metrics?.rate_limiting?.enforcements || 0,
        by_tool: metrics?.guardrails?.by_tool || {},
        by_category: metrics?.guardrails?.by_category || {},
      });
    } else {
      console.error('Failed to load gateway aggregated metrics:', metricsResult.reason);
    }
    if (eventsResult.status === 'fulfilled') {
      setEvents(eventsResult.value?.events || []);
    } else {
      console.error('Failed to load guardrails events:', eventsResult.reason);
    }

    if (metricsResult.status === 'rejected' && eventsResult.status === 'rejected') {
      const reason = metricsResult.reason;
      const message = reason instanceof Error ? reason.message : 'Failed to load guardrail metrics';
      setError(message);
    } else {
      setError(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (isReady) loadData();
  }, [isReady, loadData]);

  useEffect(() => {
    if (!isReady) return;
    const interval = setInterval(loadData, 30_000);
    return () => clearInterval(interval);
  }, [isReady, loadData]);

  const filteredEvents =
    activeFilter === 'all'
      ? events
      : events.filter((e) => ACTION_TO_FILTER[e.action] === activeFilter);

  const guardrailCards: {
    icon: typeof Fingerprint;
    title: string;
    value: number;
    description: string;
    color: string;
    filter: FilterType;
  }[] = [
    {
      icon: Fingerprint,
      title: 'PII Detection',
      value: stats?.pii_detections ?? 0,
      description: 'SSN, credit card, phone, email patterns blocked',
      color: 'text-purple-600 bg-purple-50 dark:bg-purple-900/20',
      filter: 'pii',
    },
    {
      icon: Bug,
      title: 'Injection Blocks',
      value: stats?.injection_blocks ?? 0,
      description: 'SQL, XPath, command injection attempts blocked',
      color: 'text-red-600 bg-red-50 dark:bg-red-900/20',
      filter: 'injection',
    },
    {
      icon: MessageSquareWarning,
      title: 'Prompt Guard',
      value: stats?.prompt_guard_flags ?? 0,
      description: 'LLM prompt injection attempts flagged',
      color: 'text-amber-600 bg-amber-50 dark:bg-amber-900/20',
      filter: 'prompt',
    },
    {
      icon: ShieldAlert,
      title: 'Content Filters',
      value: stats?.content_filters ?? 0,
      description: 'MIME type and body size violations',
      color: 'text-blue-600 bg-blue-50 dark:bg-blue-900/20',
      filter: 'content',
    },
    {
      icon: Zap,
      title: 'Rate Limit',
      value: stats?.rate_limit_enforcements ?? 0,
      description: 'Requests throttled by token bucket',
      color: 'text-orange-600 bg-orange-50 dark:bg-orange-900/20',
      filter: 'all',
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

      {/* Guardrail Cards — click filters the events table below */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {guardrailCards.map((card) => (
          <button
            key={card.title}
            onClick={() => setActiveFilter((prev) => (prev === card.filter ? 'all' : card.filter))}
            className={`rounded-lg border p-5 text-left transition-all ${card.color} ${
              activeFilter === card.filter
                ? 'ring-2 ring-current border-current'
                : 'border-neutral-200 dark:border-neutral-700'
            } ${card.value > 0 ? 'cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-current' : 'opacity-60'}`}
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
          </button>
        ))}
      </div>

      {/* Recent Events — each row links to trace detail */}
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
          <div className="p-8 text-center text-neutral-400 text-sm">
            {events.length === 0
              ? 'No guardrail events in the last hour'
              : `No ${FILTER_LABELS[activeFilter].toLowerCase()} events found`}
          </div>
        ) : (
          <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {filteredEvents.map((event) => {
              const badge = ACTION_BADGE[event.action] || {
                label: event.action,
                className:
                  'bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300',
              };
              return (
                <button
                  key={event.span_id}
                  onClick={() => navigate(`/call-flow/trace/${event.trace_id}`)}
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
