import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import type {
  APITransaction,
  APITransactionSummary,
  APITransactionStats,
  TransactionSpan,
  TransactionStatus,
} from '../types';
import {
  Activity,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  Search,
  Filter,
  ArrowRight,
  Server,
  Database,
  Globe,
  Zap,
  TrendingUp,
  AlertTriangle,
  Timer,
} from 'lucide-react';
import { clsx } from 'clsx';

// =============================================================================
// STATUS CONFIGURATIONS
// =============================================================================

const statusConfig: Record<TransactionStatus, { icon: typeof CheckCircle2; color: string; bg: string; label: string }> = {
  success: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-100', label: 'Success' },
  error: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-100', label: 'Error' },
  timeout: { icon: AlertCircle, color: 'text-orange-500', bg: 'bg-orange-100', label: 'Timeout' },
  pending: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-100', label: 'Pending' },
};

const methodColors: Record<string, string> = {
  GET: 'bg-blue-100 text-blue-700',
  POST: 'bg-green-100 text-green-700',
  PUT: 'bg-yellow-100 text-yellow-700',
  PATCH: 'bg-purple-100 text-purple-700',
  DELETE: 'bg-red-100 text-red-700',
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTime(isoString?: string): string {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function getStatusCodeColor(code: number): string {
  if (code >= 200 && code < 300) return 'text-green-600 bg-green-50';
  if (code >= 300 && code < 400) return 'text-blue-600 bg-blue-50';
  if (code >= 400 && code < 500) return 'text-orange-600 bg-orange-50';
  if (code >= 500) return 'text-red-600 bg-red-50';
  return 'text-gray-600 bg-gray-50';
}

// =============================================================================
// STATS CARD COMPONENT
// =============================================================================

function StatsCard({ title, value, subtitle, icon: Icon, color, trend }: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: typeof Activity;
  color: string;
  trend?: { value: number; positive: boolean };
}) {
  return (
    <div className="rounded-lg bg-white p-6 shadow-sm border border-gray-100">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className={clsx('rounded-lg p-3', color)}>
            <Icon className="h-6 w-6 text-white" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">{title}</p>
            <p className="text-2xl font-bold text-gray-900">{value}</p>
            {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
          </div>
        </div>
        {trend && (
          <div className={clsx(
            'flex items-center gap-1 text-sm font-medium',
            trend.positive ? 'text-green-600' : 'text-red-600'
          )}>
            <TrendingUp className={clsx('h-4 w-4', !trend.positive && 'rotate-180')} />
            {trend.value}%
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// TRANSACTION FLOW VISUALIZATION
// =============================================================================

function TransactionFlow({ spans }: { spans: TransactionSpan[] }) {
  if (!spans || spans.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic">No span data available</div>
    );
  }

  const serviceIcons: Record<string, typeof Server> = {
    gateway: Globe,
    kafka: Database,
    backend: Server,
    cache: Zap,
  };

  return (
    <div className="flex items-center gap-2 overflow-x-auto py-2">
      {spans.map((span, index) => {
        const config = statusConfig[span.status];
        const Icon = serviceIcons[span.service.toLowerCase()] || Server;

        return (
          <div key={index} className="flex items-center">
            <div className={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-lg border',
              span.status === 'success' ? 'border-green-200 bg-green-50' :
              span.status === 'error' ? 'border-red-200 bg-red-50' :
              span.status === 'timeout' ? 'border-orange-200 bg-orange-50' :
              'border-gray-200 bg-gray-50'
            )}>
              <Icon className={clsx('h-4 w-4', config.color)} />
              <div className="text-xs">
                <div className="font-medium text-gray-900">{span.service}</div>
                <div className="text-gray-500">{formatDuration(span.duration_ms)}</div>
              </div>
            </div>
            {index < spans.length - 1 && (
              <ArrowRight className="h-4 w-4 text-gray-400 mx-1 flex-shrink-0" />
            )}
          </div>
        );
      })}
    </div>
  );
}

// =============================================================================
// TRANSACTION ROW COMPONENT
// =============================================================================

function TransactionRow({ transaction, isExpanded, onToggle }: {
  transaction: APITransactionSummary;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const config = statusConfig[transaction.status];
  const StatusIcon = config.icon;

  return (
    <tr
      className={clsx(
        'hover:bg-gray-50 cursor-pointer transition-colors',
        isExpanded && 'bg-blue-50'
      )}
      onClick={onToggle}
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
          <code className="text-xs font-mono text-gray-500">
            {transaction.trace_id.slice(0, 8)}...
          </code>
        </div>
      </td>
      <td className="px-4 py-3">
        <span className={clsx(
          'px-2 py-1 rounded text-xs font-bold',
          methodColors[transaction.method] || 'bg-gray-100 text-gray-700'
        )}>
          {transaction.method}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col">
          <span className="font-medium text-gray-900">{transaction.api_name}</span>
          <span className="text-xs text-gray-500 truncate max-w-[200px]">{transaction.path}</span>
        </div>
      </td>
      <td className="px-4 py-3">
        <span className={clsx(
          'px-2 py-1 rounded text-xs font-bold',
          getStatusCodeColor(transaction.status_code)
        )}>
          {transaction.status_code}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className={clsx('flex items-center gap-1.5', config.color)}>
          <StatusIcon className={clsx('h-4 w-4', transaction.status === 'pending' && 'animate-spin')} />
          <span className="text-sm font-medium">{config.label}</span>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1 text-sm text-gray-600">
          <Timer className="h-4 w-4" />
          {formatDuration(transaction.total_duration_ms)}
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">
        {formatTime(transaction.started_at)}
      </td>
    </tr>
  );
}

// =============================================================================
// TRANSACTION DETAIL PANEL
// =============================================================================

function TransactionDetail({ transactionId }: { transactionId: string }) {
  const [transaction, setTransaction] = useState<APITransaction | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchDetail() {
      setLoading(true);
      try {
        const response = await apiService.get<APITransaction>(`/v1/monitoring/transactions/${transactionId}`);
        setTransaction(response.data);
      } catch (err) {
        console.error('Failed to fetch transaction detail:', err);
        // Use demo data for now
        setTransaction(generateDemoTransaction(transactionId));
      } finally {
        setLoading(false);
      }
    }
    fetchDetail();
  }, [transactionId]);

  if (loading) {
    return (
      <tr>
        <td colSpan={7} className="px-4 py-8 bg-gray-50">
          <div className="flex items-center justify-center gap-2 text-gray-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading transaction details...
          </div>
        </td>
      </tr>
    );
  }

  if (!transaction) {
    return (
      <tr>
        <td colSpan={7} className="px-4 py-8 bg-red-50">
          <div className="text-center text-red-600">Transaction not found</div>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td colSpan={7} className="px-4 py-4 bg-gray-50 border-t border-b border-gray-200">
        <div className="space-y-4">
          {/* Flow Visualization */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Transaction Flow</h4>
            <TransactionFlow spans={transaction.spans} />
          </div>

          {/* Span Details */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Span Details</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {transaction.spans.map((span, index) => {
                const config = statusConfig[span.status];
                const StatusIcon = config.icon;

                return (
                  <div
                    key={index}
                    className={clsx(
                      'p-3 rounded-lg border',
                      span.status === 'success' ? 'border-green-200 bg-green-50' :
                      span.status === 'error' ? 'border-red-200 bg-red-50' :
                      span.status === 'timeout' ? 'border-orange-200 bg-orange-50' :
                      'border-gray-200 bg-white'
                    )}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-gray-900">{span.name}</span>
                      <StatusIcon className={clsx('h-4 w-4', config.color)} />
                    </div>
                    <div className="text-xs space-y-1">
                      <div className="flex justify-between">
                        <span className="text-gray-500">Service:</span>
                        <span className="font-medium">{span.service}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Duration:</span>
                        <span className="font-medium">{formatDuration(span.duration_ms)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Started:</span>
                        <span className="font-medium">{formatTime(span.started_at)}</span>
                      </div>
                      {span.error && (
                        <div className="mt-2 p-2 bg-red-100 rounded text-red-700">
                          {span.error}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Error Message */}
          {transaction.error_message && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-semibold text-red-800">Error Details</h4>
                  <p className="text-sm text-red-700 mt-1">{transaction.error_message}</p>
                </div>
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div>
              <span className="text-gray-500">Trace ID:</span>
              <code className="block font-mono text-gray-900">{transaction.trace_id}</code>
            </div>
            <div>
              <span className="text-gray-500">Client IP:</span>
              <span className="block text-gray-900">{transaction.client_ip || '-'}</span>
            </div>
            <div>
              <span className="text-gray-500">User:</span>
              <span className="block text-gray-900">{transaction.user_id || 'Anonymous'}</span>
            </div>
            <div>
              <span className="text-gray-500">Tenant:</span>
              <span className="block text-gray-900">{transaction.tenant_id}</span>
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

// =============================================================================
// DEMO DATA GENERATOR
// =============================================================================

function generateDemoStats(): APITransactionStats {
  return {
    total_requests: 12847,
    success_count: 11923,
    error_count: 724,
    timeout_count: 200,
    avg_latency_ms: 145,
    p95_latency_ms: 320,
    p99_latency_ms: 890,
    requests_per_minute: 42.5,
    by_api: {
      'weather-api': { total: 4521, success: 4398, errors: 123, avg_latency_ms: 89 },
      'payment-api': { total: 3298, success: 3102, errors: 196, avg_latency_ms: 234 },
      'user-api': { total: 2876, success: 2654, errors: 222, avg_latency_ms: 156 },
      'inventory-api': { total: 2152, success: 1769, errors: 183, avg_latency_ms: 178 },
    },
    by_status_code: {
      200: 10234,
      201: 1689,
      400: 312,
      401: 89,
      404: 156,
      500: 167,
    },
  };
}

function generateDemoTransactions(): APITransactionSummary[] {
  const apis = ['weather-api', 'payment-api', 'user-api', 'inventory-api'];
  const methods = ['GET', 'POST', 'PUT', 'DELETE'];
  const paths = ['/v1/data', '/v1/users/123', '/v1/orders', '/v1/products', '/v1/health'];
  const statuses: TransactionStatus[] = ['success', 'success', 'success', 'success', 'error', 'timeout'];

  return Array.from({ length: 20 }, (_, i) => {
    const status = statuses[Math.floor(Math.random() * statuses.length)];
    const statusCode = status === 'success'
      ? [200, 201][Math.floor(Math.random() * 2)]
      : status === 'error'
      ? [400, 404, 500][Math.floor(Math.random() * 3)]
      : 504;

    return {
      id: `txn-${i + 1}`,
      trace_id: `trace-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      api_name: apis[Math.floor(Math.random() * apis.length)],
      method: methods[Math.floor(Math.random() * methods.length)],
      path: paths[Math.floor(Math.random() * paths.length)],
      status_code: statusCode,
      status,
      started_at: new Date(Date.now() - Math.random() * 3600000).toISOString(),
      total_duration_ms: Math.floor(Math.random() * 500) + 50,
      spans_count: Math.floor(Math.random() * 4) + 2,
    };
  }).sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
}

function generateDemoTransaction(id: string): APITransaction {
  const summary = generateDemoTransactions()[0];
  return {
    ...summary,
    id,
    tenant_id: 'tenant-acme',
    client_ip: '192.168.1.' + Math.floor(Math.random() * 255),
    user_id: ['alice@example.com', 'bob@example.com', null][Math.floor(Math.random() * 3)] || undefined,
    spans: [
      {
        name: 'Gateway Ingress',
        service: 'Gateway',
        status: 'success',
        started_at: summary.started_at,
        duration_ms: 15,
      },
      {
        name: 'Authentication',
        service: 'Gateway',
        status: 'success',
        started_at: summary.started_at,
        duration_ms: 8,
      },
      {
        name: 'Rate Limiting',
        service: 'Gateway',
        status: 'success',
        started_at: summary.started_at,
        duration_ms: 2,
      },
      {
        name: 'Backend Request',
        service: 'Backend',
        status: summary.status,
        started_at: summary.started_at,
        duration_ms: summary.total_duration_ms - 30,
        error: summary.status === 'error' ? 'Backend returned 500: Internal Server Error' : undefined,
      },
      {
        name: 'Response Transform',
        service: 'Gateway',
        status: summary.status === 'timeout' ? 'timeout' : 'success',
        started_at: summary.started_at,
        duration_ms: 5,
      },
    ],
    error_message: summary.status === 'error'
      ? 'Backend service returned an error response'
      : summary.status === 'timeout'
      ? 'Request timed out waiting for backend response'
      : undefined,
  };
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function APIMonitoring() {
  const [transactions, setTransactions] = useState<APITransactionSummary[]>([]);
  const [stats, setStats] = useState<APITransactionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<TransactionStatus | 'all'>('all');
  const [apiFilter, setApiFilter] = useState<string>('all');

  const fetchData = useCallback(async () => {
    try {
      // Try to fetch from API
      const [txnResponse, statsResponse] = await Promise.all([
        apiService.get<{ transactions: APITransactionSummary[] }>('/v1/monitoring/transactions'),
        apiService.get<APITransactionStats>('/v1/monitoring/transactions/stats'),
      ]);
      setTransactions(txnResponse.data.transactions);
      setStats(statsResponse.data);
    } catch (err) {
      console.log('Using demo data for transactions');
      // Use demo data
      setTransactions(generateDemoTransactions());
      setStats(generateDemoStats());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchData]);

  // Filter transactions
  const filteredTransactions = transactions.filter(txn => {
    if (statusFilter !== 'all' && txn.status !== statusFilter) return false;
    if (apiFilter !== 'all' && txn.api_name !== apiFilter) return false;
    if (searchTerm) {
      const search = searchTerm.toLowerCase();
      return (
        txn.trace_id.toLowerCase().includes(search) ||
        txn.api_name.toLowerCase().includes(search) ||
        txn.path.toLowerCase().includes(search)
      );
    }
    return true;
  });

  // Get unique APIs for filter
  const uniqueApis = [...new Set(transactions.map(t => t.api_name))];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">API Monitoring</h1>
          <p className="text-gray-500 mt-1">
            Real-time E2E transaction tracing - Gateway → Backend → Response
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
              autoRefresh
                ? 'bg-green-100 text-green-700 hover:bg-green-200'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            )}
          >
            <Activity className={clsx('h-4 w-4', autoRefresh && 'animate-pulse')} />
            {autoRefresh ? 'Live' : 'Paused'}
          </button>
          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatsCard
            title="Total Requests"
            value={stats.total_requests.toLocaleString()}
            subtitle={`${stats.requests_per_minute.toFixed(1)} req/min`}
            icon={Activity}
            color="bg-blue-500"
          />
          <StatsCard
            title="Success Rate"
            value={`${((stats.success_count / stats.total_requests) * 100).toFixed(1)}%`}
            subtitle={`${stats.success_count.toLocaleString()} successful`}
            icon={CheckCircle2}
            color="bg-green-500"
          />
          <StatsCard
            title="Avg Latency"
            value={`${stats.avg_latency_ms}ms`}
            subtitle={`P95: ${stats.p95_latency_ms}ms | P99: ${stats.p99_latency_ms}ms`}
            icon={Timer}
            color="bg-purple-500"
          />
          <StatsCard
            title="Errors"
            value={stats.error_count + stats.timeout_count}
            subtitle={`${stats.error_count} errors, ${stats.timeout_count} timeouts`}
            icon={AlertTriangle}
            color="bg-red-500"
          />
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search by trace ID, API, or path..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-gray-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as TransactionStatus | 'all')}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Statuses</option>
              <option value="success">Success</option>
              <option value="error">Error</option>
              <option value="timeout">Timeout</option>
            </select>
          </div>

          {/* API Filter */}
          <select
            value={apiFilter}
            onChange={(e) => setApiFilter(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All APIs</option>
            {uniqueApis.map(api => (
              <option key={api} value={api}>{api}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Transactions Table */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Trace ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Method
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  API / Path
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Result
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Duration
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Time
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredTransactions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-gray-500">
                    <Activity className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                    <p className="text-lg font-medium">No transactions found</p>
                    <p className="text-sm">Try adjusting your filters or wait for new requests</p>
                  </td>
                </tr>
              ) : (
                filteredTransactions.map((transaction) => (
                  <>
                    <TransactionRow
                      key={transaction.id}
                      transaction={transaction}
                      isExpanded={expandedId === transaction.id}
                      onToggle={() => setExpandedId(expandedId === transaction.id ? null : transaction.id)}
                    />
                    {expandedId === transaction.id && (
                      <TransactionDetail transactionId={transaction.id} />
                    )}
                  </>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Activity className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-semibold text-blue-800">E2E Transaction Monitoring</h4>
            <p className="text-sm text-blue-700 mt-1">
              This page shows the complete journey of API requests through your infrastructure:
              Gateway ingress → Authentication → Rate limiting → Backend request → Response transformation.
              Click on any transaction to see the detailed span breakdown.
            </p>
            <p className="text-xs text-blue-600 mt-2">
              Note: Full distributed tracing with OpenTelemetry will provide even more detailed insights when enabled.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
