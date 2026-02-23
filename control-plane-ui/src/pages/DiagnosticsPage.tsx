import { useState, memo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  ShieldAlert,
  RefreshCw,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Wifi,
  Clock,
  ChevronRight,
} from 'lucide-react';
import { runDiagnostic, checkConnectivity } from '../services/diagnosticService';
import type { RootCause } from '../services/diagnosticService';
import { apiService } from '../services/api';

// --- Gateway selector types ---
interface GatewayOption {
  id: string;
  name: string;
}

// --- Confidence color mapping ---
const confidenceColor = (c: number) => {
  if (c >= 0.9) return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
  if (c >= 0.7) return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400';
  return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400';
};

// --- Sub-components ---
const RootCauseBadge = memo(function RootCauseBadge({ cause }: { cause: RootCause }) {
  return (
    <div className="flex items-start gap-3 p-3 bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700">
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${confidenceColor(cause.confidence)}`}
      >
        {Math.round(cause.confidence * 100)}%
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-white capitalize">
          {cause.category.replace('_', ' ')}
        </p>
        <p className="text-xs text-gray-500 dark:text-neutral-400 mt-0.5">{cause.summary}</p>
        {cause.evidence.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {cause.evidence.map((e, i) => (
              <li
                key={i}
                className="text-xs text-gray-400 dark:text-neutral-500 flex items-center gap-1"
              >
                <ChevronRight className="w-3 h-3 flex-shrink-0" />
                {e}
              </li>
            ))}
          </ul>
        )}
        {cause.suggested_fix && (
          <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
            Fix: {cause.suggested_fix}
          </p>
        )}
      </div>
    </div>
  );
});

// --- Main page ---
export function DiagnosticsPage() {
  const { t } = useTranslation();
  const [selectedGateway, setSelectedGateway] = useState<string>('');

  // Fetch available gateways
  const { data: gateways = [], isLoading: gatewaysLoading } = useQuery({
    queryKey: ['gateways-list'],
    queryFn: async () => {
      const { data } = await apiService.get<GatewayOption[]>('/v1/admin/gateways');
      return data;
    },
    staleTime: 60_000,
  });

  // Run diagnostic on selected gateway
  const {
    data: report,
    isLoading: diagLoading,
    error: diagError,
    refetch: runDiag,
  } = useQuery({
    queryKey: ['diagnostic', selectedGateway],
    queryFn: () => runDiagnostic(selectedGateway),
    enabled: !!selectedGateway,
    refetchInterval: 30_000,
  });

  // Connectivity check
  const {
    data: connectivity,
    isLoading: connLoading,
    refetch: runConn,
  } = useQuery({
    queryKey: ['connectivity', selectedGateway],
    queryFn: () => checkConnectivity(selectedGateway),
    enabled: false,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <ShieldAlert className="w-6 h-6" />
            {t('diagnostics.title', 'Platform Diagnostics')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
            {t('diagnostics.description', 'Automated root cause analysis and connectivity testing')}
          </p>
        </div>
        <button
          onClick={() => runDiag()}
          disabled={!selectedGateway || diagLoading}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${diagLoading ? 'animate-spin' : ''}`} />
          Run Diagnostic
        </button>
      </div>

      {/* Gateway selector */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-4">
        <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-2">
          Select Gateway
        </label>
        {gatewaysLoading ? (
          <div className="flex items-center gap-2 text-gray-400">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading gateways...
          </div>
        ) : (
          <select
            value={selectedGateway}
            onChange={(e) => setSelectedGateway(e.target.value)}
            className="block w-full max-w-md rounded-md border border-gray-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          >
            <option value="">Choose a gateway...</option>
            {gateways.map((gw) => (
              <option key={gw.id} value={gw.id}>
                {gw.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Diagnostic results */}
      {diagError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <XCircle className="w-5 h-5 text-red-500" />
            <span className="text-red-800 dark:text-red-300 font-medium">Diagnostic failed</span>
          </div>
          <p className="text-sm text-red-600 dark:text-red-400 mt-1">
            {(diagError as Error).message}
          </p>
        </div>
      )}

      {diagLoading && selectedGateway && (
        <div className="flex items-center gap-3 p-6 bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700">
          <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
          <span className="text-gray-600 dark:text-neutral-300">
            Running diagnostic analysis...
          </span>
        </div>
      )}

      {report && !diagLoading && (
        <div className="space-y-4">
          {/* Root causes */}
          <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              Root Causes
              {report.root_causes.length === 0 && (
                <span className="text-sm font-normal text-green-600 dark:text-green-400 ml-2">
                  No issues detected
                </span>
              )}
            </h2>
            {report.root_causes.length > 0 ? (
              <div className="space-y-2">
                {report.root_causes.map((cause, i) => (
                  <RootCauseBadge key={i} cause={cause} />
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-green-600 dark:text-green-400 p-3">
                <CheckCircle2 className="w-5 h-5" />
                <span>All systems healthy — no root causes identified.</span>
              </div>
            )}
          </div>

          {/* Timing breakdown */}
          {report.timing && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <Clock className="w-5 h-5" />
                Timing Breakdown
              </h2>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-3 bg-gray-50 dark:bg-neutral-700/50 rounded-lg">
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">
                    {report.timing.gateway_ms?.toFixed(0) ?? '—'}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">Gateway (ms)</p>
                </div>
                <div className="text-center p-3 bg-gray-50 dark:bg-neutral-700/50 rounded-lg">
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">
                    {report.timing.backend_ms?.toFixed(0) ?? '—'}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">Backend (ms)</p>
                </div>
                <div className="text-center p-3 bg-gray-50 dark:bg-neutral-700/50 rounded-lg">
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">
                    {report.timing.total_ms?.toFixed(0) ?? '—'}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">Total (ms)</p>
                </div>
              </div>
            </div>
          )}

          {/* Network path */}
          {report.network_path && (
            <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <Activity className="w-5 h-5" />
                Network Path ({report.network_path.total_hops} hops)
              </h2>
              <div className="flex items-center gap-2 overflow-x-auto pb-2">
                {report.network_path.hops.map((hop, i) => (
                  <div key={i} className="flex items-center gap-2">
                    {i > 0 && <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />}
                    <div className="px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md text-sm whitespace-nowrap">
                      <span className="font-medium text-blue-800 dark:text-blue-300">
                        {hop.pseudonym}
                      </span>
                      <span className="text-blue-500 dark:text-blue-400 ml-1 text-xs">
                        {hop.protocol}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Connectivity check */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 shadow-sm p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Wifi className="w-5 h-5" />
            Connectivity Test
          </h2>
          <button
            onClick={() => runConn()}
            disabled={!selectedGateway || connLoading}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-neutral-200 bg-gray-100 dark:bg-neutral-700 hover:bg-gray-200 dark:hover:bg-neutral-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-md transition-colors"
          >
            {connLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Wifi className="w-4 h-4" />
            )}
            Check Connectivity
          </button>
        </div>

        {connectivity && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 mb-2">
              {connectivity.overall_status === 'healthy' ? (
                <CheckCircle2 className="w-5 h-5 text-green-500" />
              ) : (
                <XCircle className="w-5 h-5 text-red-500" />
              )}
              <span
                className={`font-medium ${connectivity.overall_status === 'healthy' ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}
              >
                {connectivity.overall_status === 'healthy'
                  ? 'All stages passed'
                  : 'Issues detected'}
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {connectivity.stages.map((stage) => (
                <div
                  key={stage.name}
                  className={`p-2 rounded-md border text-center ${
                    stage.status === 'ok'
                      ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20'
                      : 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20'
                  }`}
                >
                  <p className="text-xs font-medium text-gray-700 dark:text-neutral-300 capitalize">
                    {stage.name}
                  </p>
                  <p
                    className={`text-sm font-bold ${stage.status === 'ok' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
                  >
                    {stage.status === 'ok' ? '✓' : '✗'}
                  </p>
                  {stage.latency_ms !== null && (
                    <p className="text-xs text-gray-400 dark:text-neutral-500">
                      {stage.latency_ms.toFixed(0)}ms
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {!connectivity && !connLoading && (
          <p className="text-sm text-gray-400 dark:text-neutral-500">
            Select a gateway and click &quot;Check Connectivity&quot; to test the chain.
          </p>
        )}
      </div>
    </div>
  );
}
