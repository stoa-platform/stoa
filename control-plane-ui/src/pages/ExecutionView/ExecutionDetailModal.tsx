/**
 * Execution Detail Modal — Full execution trace (CAB-1318)
 */

interface ExecutionDetail {
  id: string;
  tenant_id: string;
  consumer_id: string | null;
  api_id: string | null;
  api_name: string | null;
  tool_name: string | null;
  request_id: string;
  method: string | null;
  path: string | null;
  status_code: number | null;
  status: string;
  error_category: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  request_headers: Record<string, unknown> | null;
  response_summary: Record<string, unknown> | null;
}

interface ExecutionDetailModalProps {
  execution: ExecutionDetail;
  onClose: () => void;
}

export function ExecutionDetailModal({ execution, onClose }: ExecutionDetailModalProps) {
  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
      role="dialog"
      aria-label="Execution Detail"
    >
      <div
        className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Execution Detail</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:text-neutral-400 dark:hover:text-neutral-200"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Request ID" value={execution.request_id} />
            <Field label="Status" value={`${execution.status_code ?? '—'} (${execution.status})`} />
            <Field label="Method" value={execution.method} />
            <Field label="Path" value={execution.path} />
            <Field label="API" value={execution.api_name} />
            <Field label="Tool" value={execution.tool_name} />
            <Field
              label="Duration"
              value={execution.duration_ms != null ? `${execution.duration_ms}ms` : null}
            />
            <Field label="Error Category" value={execution.error_category} />
            <Field label="Consumer ID" value={execution.consumer_id} />
            <Field
              label="Started At"
              value={execution.started_at ? new Date(execution.started_at).toLocaleString() : null}
            />
          </div>

          {execution.error_message && (
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                Error Message
              </p>
              <pre className="text-sm bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 p-3 rounded-md overflow-x-auto">
                {execution.error_message}
              </pre>
            </div>
          )}

          {execution.request_headers && (
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                Request Headers
              </p>
              <pre className="text-xs bg-gray-50 dark:bg-neutral-900 text-gray-700 dark:text-neutral-300 p-3 rounded-md overflow-x-auto">
                {JSON.stringify(execution.request_headers, null, 2)}
              </pre>
            </div>
          )}

          {execution.response_summary && (
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                Response Summary
              </p>
              <pre className="text-xs bg-gray-50 dark:bg-neutral-900 text-gray-700 dark:text-neutral-300 p-3 rounded-md overflow-x-auto">
                {JSON.stringify(execution.response_summary, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <p className="text-xs text-gray-500 dark:text-neutral-400">{label}</p>
      <p className="text-sm font-medium text-gray-900 dark:text-white">{value || '—'}</p>
    </div>
  );
}
