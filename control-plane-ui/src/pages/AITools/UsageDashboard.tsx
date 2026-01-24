import { useState, useEffect } from 'react';
import {
  Activity,
  TrendingUp,
  Clock,
  DollarSign,
  AlertCircle,
  Calendar,
  BarChart3,
} from 'lucide-react';
import { mcpGatewayService } from '../../services/mcpGatewayApi';
import { UsageChart, UsageStatsCard } from '../../components/tools';
import type { ToolUsageSummary } from '../../types';

type PeriodType = 'day' | 'week' | 'month';

interface DataPoint {
  timestamp: string;
  calls: number;
  successRate: number;
  avgLatencyMs: number;
  costUnits: number;
}

export function UsageDashboard() {
  // State
  const [usage, setUsage] = useState<ToolUsageSummary | null>(null);
  const [history, setHistory] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<PeriodType>('week');

  // Load data
  useEffect(() => {
    async function loadUsage() {
      try {
        setLoading(true);
        setError(null);

        const [usageData, historyData] = await Promise.all([
          mcpGatewayService.getMyUsage({ period }),
          mcpGatewayService.getUsageHistory({
            period,
            groupBy: period === 'day' ? 'hour' : 'day',
          }),
        ]);

        setUsage(usageData);
        setHistory(historyData.dataPoints || []);
      } catch (err) {
        console.error('Failed to load usage:', err);
        setError(err instanceof Error ? err.message : 'Failed to load usage data');
      } finally {
        setLoading(false);
      }
    }

    loadUsage();
  }, [period]);

  const periodOptions: { value: PeriodType; label: string }[] = [
    { value: 'day', label: 'Last 24 hours' },
    { value: 'week', label: 'Last 7 days' },
    { value: 'month', label: 'Last 30 days' },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Usage Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            Monitor your AI tool usage and costs
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Period Selector */}
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-gray-400" />
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value as PeriodType)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {periodOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {usage ? (
        <>
          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <UsageStatsCard
              title="Total Calls"
              value={usage.totalCalls.toLocaleString()}
              subtitle={`${usage.period}`}
              icon={<Activity className="h-5 w-5" />}
              color="blue"
            />
            <UsageStatsCard
              title="Success Rate"
              value={`${(usage.successRate * 100).toFixed(1)}%`}
              subtitle="Successful invocations"
              icon={<TrendingUp className="h-5 w-5" />}
              color="green"
            />
            <UsageStatsCard
              title="Avg Latency"
              value={`${usage.avgLatencyMs.toFixed(0)}ms`}
              subtitle="Response time"
              icon={<Clock className="h-5 w-5" />}
              color="orange"
            />
            <UsageStatsCard
              title="Total Cost"
              value={`$${usage.totalCostUnits.toFixed(4)}`}
              subtitle="Cost units"
              icon={<DollarSign className="h-5 w-5" />}
              color="purple"
            />
          </div>

          {/* Charts */}
          {history.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <UsageChart
                data={history}
                metric="calls"
                title="API Calls"
                height={200}
              />
              <UsageChart
                data={history}
                metric="successRate"
                title="Success Rate"
                height={200}
              />
              <UsageChart
                data={history}
                metric="avgLatencyMs"
                title="Average Latency (ms)"
                height={200}
              />
              <UsageChart
                data={history}
                metric="costUnits"
                title="Cost Units"
                height={200}
              />
            </div>
          )}

          {/* Tool Breakdown */}
          {usage.toolBreakdown && usage.toolBreakdown.length > 0 && (
            <div className="bg-white rounded-lg border border-gray-200">
              <div className="px-6 py-4 border-b border-gray-200">
                <h3 className="text-lg font-medium text-gray-900">Usage by Tool</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Tool
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Calls
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Success
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Errors
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Avg Latency
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Cost
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {usage.toolBreakdown.map((tool) => (
                      <tr key={tool.toolName} className="hover:bg-gray-50">
                        <td className="px-6 py-4 text-sm font-medium text-gray-900">
                          {tool.toolName}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600 text-right">
                          {tool.totalCalls.toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-sm text-green-600 text-right">
                          {tool.successCount.toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-sm text-red-600 text-right">
                          {tool.errorCount.toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600 text-right">
                          {tool.avgLatencyMs.toFixed(0)}ms
                        </td>
                        <td className="px-6 py-4 text-sm text-purple-600 text-right">
                          ${tool.totalCostUnits.toFixed(4)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Period Info */}
          <div className="text-sm text-gray-500 text-center">
            Showing data from {new Date(usage.startDate).toLocaleDateString()} to{' '}
            {new Date(usage.endDate).toLocaleDateString()}
          </div>
        </>
      ) : (
        <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
          <BarChart3 className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No usage data yet</h3>
          <p className="text-sm text-gray-500">
            Start using AI tools to see your usage metrics here
          </p>
        </div>
      )}
    </div>
  );
}
