import { ClipboardList } from 'lucide-react';

export function AuditLog() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Audit Log</h1>
        <p className="text-gray-500 dark:text-neutral-400 mt-2">
          Track all platform actions, configuration changes, and access events
        </p>
      </div>

      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-8 text-center">
        <div className="w-16 h-16 bg-primary-100 dark:bg-primary-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
          <ClipboardList className="h-8 w-8 text-primary-600 dark:text-primary-400" />
        </div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Coming Soon</h2>
        <p className="text-gray-500 dark:text-neutral-400 max-w-md mx-auto">
          The Audit Log will provide a comprehensive timeline of all actions performed on the
          platform, with filtering, search, and export capabilities for compliance needs.
        </p>
      </div>
    </div>
  );
}

export default AuditLog;
