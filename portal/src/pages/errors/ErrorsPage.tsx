import { useState, useEffect, useCallback } from 'react';
import { AlertCircle, RefreshCw, Loader2 } from 'lucide-react';
import { errorSnapshotsService } from '../../services/errorSnapshots';
import { SnapshotDetail } from './SnapshotDetail';
import type { ErrorSnapshot, SnapshotSummary, ResolutionStatus } from '../../types';

const statusCodeColor: Record<string, string> = {
  '4': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-400',
  '5': 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-400',
};

const resolutionColors: Record<ResolutionStatus, string> = {
  unresolved: 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-400',
  investigating: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-400',
  resolved: 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-400',
  ignored: 'bg-gray-100 dark:bg-neutral-700 text-gray-600 dark:text-neutral-400',
};

function StatusCodeBadge({ code }: { code: number }) {
  const prefix = String(code)[0];
  const color =
    statusCodeColor[prefix] ||
    'bg-gray-100 dark:bg-neutral-700 text-gray-800 dark:text-neutral-300';
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium ${color}`}
    >
      {code}
    </span>
  );
}

function ResolutionBadge({ resolution }: { resolution: ResolutionStatus }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${resolutionColors[resolution]}`}
    >
      {resolution}
    </span>
  );
}

function StatsCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
      <p className="text-sm text-gray-500 dark:text-neutral-400">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

export function ErrorsPage() {
  const [snapshots, setSnapshots] = useState<ErrorSnapshot[]>([]);
  const [stats, setStats] = useState<SnapshotSummary | null>(null);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [triggerFilter, setTriggerFilter] = useState('');
  const [resolutionFilter, setResolutionFilter] = useState('');
  const [selectedSnapshot, setSelectedSnapshot] = useState<ErrorSnapshot | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    const [listData, statsData] = await Promise.all([
      errorSnapshotsService.listSnapshots({
        trigger: triggerFilter || undefined,
        resolution: resolutionFilter || undefined,
      }),
      errorSnapshotsService.getStats(),
    ]);
    setSnapshots(listData.items);
    setTotal(listData.total);
    setStats(statsData);
    setIsLoading(false);
  }, [triggerFilter, resolutionFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSnapshotClick = async (snapshot: ErrorSnapshot) => {
    const full = await errorSnapshotsService.getSnapshot(snapshot.id);
    if (full) setSelectedSnapshot(full);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Error Snapshots</h1>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
            Time-travel debugging &mdash; {total} snapshot{total !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={fetchData}
          className="inline-flex items-center px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-md text-sm font-medium text-gray-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 hover:bg-gray-50 dark:hover:bg-neutral-700 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatsCard label="Total" value={stats.total} color="text-gray-900 dark:text-white" />
          <StatsCard
            label="4xx Errors"
            value={stats.by_trigger['4xx'] || 0}
            color="text-yellow-600"
          />
          <StatsCard label="5xx Errors" value={stats.by_trigger['5xx'] || 0} color="text-red-600" />
          <StatsCard
            label="Unresolved"
            value={stats.unresolved_count}
            color="text-red-600 dark:text-red-400"
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={triggerFilter}
          onChange={(e) => setTriggerFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-md text-sm bg-white dark:bg-neutral-800 text-gray-700 dark:text-neutral-300"
        >
          <option value="">All Triggers</option>
          <option value="4xx">4xx</option>
          <option value="5xx">5xx</option>
          <option value="timeout">Timeout</option>
          <option value="manual">Manual</option>
        </select>
        <select
          value={resolutionFilter}
          onChange={(e) => setResolutionFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-md text-sm bg-white dark:bg-neutral-800 text-gray-700 dark:text-neutral-300"
        >
          <option value="">All Resolutions</option>
          <option value="unresolved">Unresolved</option>
          <option value="investigating">Investigating</option>
          <option value="resolved">Resolved</option>
          <option value="ignored">Ignored</option>
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      ) : snapshots.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700">
          <AlertCircle className="w-12 h-12 text-gray-300 dark:text-neutral-600 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-neutral-400 font-medium">No error snapshots</p>
          <p className="text-sm text-gray-400 dark:text-neutral-500 mt-1">
            Snapshots are captured automatically when the gateway encounters errors.
          </p>
        </div>
      ) : (
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-neutral-700">
            <thead className="bg-gray-50 dark:bg-neutral-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Timestamp
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Request
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Duration
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Trigger
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                  Resolution
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-neutral-700">
              {snapshots.map((snap) => (
                <tr
                  key={snap.id}
                  onClick={() => handleSnapshotClick(snap)}
                  className="hover:bg-gray-50 dark:hover:bg-neutral-700/50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 text-sm text-gray-500 dark:text-neutral-400 whitespace-nowrap">
                    {new Date(snap.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {snap.method}
                    </span>{' '}
                    <span className="text-sm text-gray-500 dark:text-neutral-400">{snap.path}</span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusCodeBadge code={snap.status_code} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500 dark:text-neutral-400">
                    {snap.duration_ms}ms
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700 dark:text-neutral-300">
                    {snap.trigger}
                  </td>
                  <td className="px-4 py-3">
                    <ResolutionBadge resolution={snap.resolution} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail Drawer */}
      {selectedSnapshot && (
        <SnapshotDetail
          snapshot={selectedSnapshot}
          onClose={() => setSelectedSnapshot(null)}
          onUpdate={() => {
            setSelectedSnapshot(null);
            fetchData();
          }}
        />
      )}
    </div>
  );
}
