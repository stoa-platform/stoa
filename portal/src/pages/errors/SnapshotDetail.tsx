import { useState } from 'react';
import { X, Check, Terminal } from 'lucide-react';
import { errorSnapshotsService } from '../../services/errorSnapshots';
import type { ErrorSnapshot, ResolutionStatus } from '../../types';

interface SnapshotDetailProps {
  snapshot: ErrorSnapshot;
  onClose: () => void;
  onUpdate: () => void;
}

const resolutionOptions: { value: ResolutionStatus; label: string }[] = [
  { value: 'unresolved', label: 'Unresolved' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'ignored', label: 'Ignored' },
];

const tabs = ['Overview', 'Request', 'Response', 'Policies'] as const;
type Tab = (typeof tabs)[number];

export function SnapshotDetail({ snapshot, onClose, onUpdate }: SnapshotDetailProps) {
  const [activeTab, setActiveTab] = useState<Tab>('Overview');
  const [resolution, setResolution] = useState<ResolutionStatus>(snapshot.resolution);
  const [notes, setNotes] = useState(snapshot.resolution_notes || '');
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleSaveResolution = async () => {
    setSaving(true);
    const ok = await errorSnapshotsService.updateResolution(snapshot.id, resolution, notes);
    setSaving(false);
    if (ok) onUpdate();
  };

  const handleReplay = async () => {
    const result = await errorSnapshotsService.generateReplay(snapshot.id);
    if (result?.curl_command) {
      await navigator.clipboard.writeText(result.curl_command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        tabIndex={-1}
        role="button"
        aria-label="Close drawer"
      />
      <div className="relative w-full max-w-xl bg-white dark:bg-neutral-800 shadow-xl overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-neutral-800 border-b border-gray-200 dark:border-neutral-700 px-6 py-4 flex items-center justify-between z-10">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              {snapshot.method} {snapshot.path}
            </h2>
            <p className="text-sm text-gray-500 dark:text-neutral-400">
              {new Date(snapshot.timestamp).toLocaleString()} &middot; {snapshot.status_code}{' '}
              &middot; {snapshot.duration_ms}ms
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-neutral-200 rounded"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-neutral-700 px-6">
          <div className="flex gap-4">
            {tabs.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab
                    ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                    : 'border-transparent text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-300'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {activeTab === 'Overview' && (
            <>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-gray-500 dark:text-neutral-400">Trigger</p>
                  <p className="font-medium text-gray-900 dark:text-white">{snapshot.trigger}</p>
                </div>
                <div>
                  <p className="text-gray-500 dark:text-neutral-400">Source</p>
                  <p className="font-medium text-gray-900 dark:text-white">{snapshot.source}</p>
                </div>
                {snapshot.trace_id && (
                  <div className="col-span-2">
                    <p className="text-gray-500 dark:text-neutral-400">Trace ID</p>
                    <code className="text-xs bg-gray-100 dark:bg-neutral-700 px-2 py-1 rounded">
                      {snapshot.trace_id}
                    </code>
                  </div>
                )}
              </div>

              {/* Resolution */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Resolution</h3>
                <select
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value as ResolutionStatus)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-md text-sm bg-white dark:bg-neutral-700 text-gray-900 dark:text-white"
                >
                  {resolutionOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Notes..."
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-md text-sm bg-white dark:bg-neutral-700 text-gray-900 dark:text-white placeholder-gray-400"
                />
                <button
                  onClick={handleSaveResolution}
                  disabled={saving}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 transition-colors"
                >
                  {saving ? 'Saving...' : 'Save Resolution'}
                </button>
              </div>

              {/* Replay */}
              <button
                onClick={handleReplay}
                className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 bg-white dark:bg-neutral-700 border border-gray-300 dark:border-neutral-600 rounded-md hover:bg-gray-50 dark:hover:bg-neutral-600 transition-colors"
              >
                {copied ? (
                  <Check className="w-4 h-4 text-green-500" />
                ) : (
                  <Terminal className="w-4 h-4" />
                )}
                {copied ? 'Copied!' : 'Replay cURL'}
              </button>
            </>
          )}

          {activeTab === 'Request' && (
            <div className="space-y-4">
              {snapshot.request_headers && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                    Headers
                  </h3>
                  <pre className="text-xs bg-gray-50 dark:bg-neutral-900 rounded p-3 overflow-x-auto">
                    {JSON.stringify(snapshot.request_headers, null, 2)}
                  </pre>
                </div>
              )}
              {snapshot.request_body && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Body</h3>
                  <pre className="text-xs bg-gray-50 dark:bg-neutral-900 rounded p-3 overflow-x-auto">
                    {snapshot.request_body}
                  </pre>
                </div>
              )}
              {!snapshot.request_headers && !snapshot.request_body && (
                <p className="text-sm text-gray-500 dark:text-neutral-400">
                  No request data captured.
                </p>
              )}
            </div>
          )}

          {activeTab === 'Response' && (
            <div className="space-y-4">
              {snapshot.response_headers && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                    Headers
                  </h3>
                  <pre className="text-xs bg-gray-50 dark:bg-neutral-900 rounded p-3 overflow-x-auto">
                    {JSON.stringify(snapshot.response_headers, null, 2)}
                  </pre>
                </div>
              )}
              {snapshot.response_body && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Body</h3>
                  <pre className="text-xs bg-gray-50 dark:bg-neutral-900 rounded p-3 overflow-x-auto">
                    {snapshot.response_body}
                  </pre>
                </div>
              )}
              {!snapshot.response_headers && !snapshot.response_body && (
                <p className="text-sm text-gray-500 dark:text-neutral-400">
                  No response data captured.
                </p>
              )}
            </div>
          )}

          {activeTab === 'Policies' && (
            <div className="space-y-4">
              {snapshot.policies_applied && snapshot.policies_applied.length > 0 ? (
                <div className="space-y-2">
                  {snapshot.policies_applied.map((policy) => (
                    <div
                      key={policy.name}
                      className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-neutral-900 rounded"
                    >
                      <span className="text-sm text-gray-900 dark:text-white">{policy.name}</span>
                      <div className="flex items-center gap-2">
                        {policy.duration_ms !== undefined && (
                          <span className="text-xs text-gray-500 dark:text-neutral-400">
                            {policy.duration_ms}ms
                          </span>
                        )}
                        <span
                          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                            policy.result === 'pass'
                              ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-400'
                              : policy.result === 'fail'
                                ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-400'
                                : 'bg-gray-100 dark:bg-neutral-700 text-gray-600 dark:text-neutral-400'
                          }`}
                        >
                          {policy.result}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-neutral-400">
                  No policies recorded for this snapshot.
                </p>
              )}

              {snapshot.backend_state && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                    Backend State
                  </h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-gray-500 dark:text-neutral-400">Health</p>
                      <p className="font-medium text-gray-900 dark:text-white">
                        {snapshot.backend_state.health}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500 dark:text-neutral-400">Latency</p>
                      <p className="font-medium text-gray-900 dark:text-white">
                        {snapshot.backend_state.latency_ms}ms
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
