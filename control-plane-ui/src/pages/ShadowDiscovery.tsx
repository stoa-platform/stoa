import { Eye } from 'lucide-react';

export function ShadowDiscovery() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
          Shadow API Discovery
        </h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-2">
          Automatically detect undocumented APIs and shadow endpoints across your infrastructure
        </p>
      </div>

      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-8 text-center">
        <div className="w-16 h-16 bg-primary-100 dark:bg-primary-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
          <Eye className="h-8 w-8 text-primary-600 dark:text-primary-400" />
        </div>
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-2">Coming Soon</h2>
        <p className="text-neutral-500 dark:text-neutral-400 max-w-md mx-auto">
          Shadow API Discovery will scan your network traffic to identify undocumented APIs, helping
          you maintain a complete API inventory and reduce security risks.
        </p>
      </div>
    </div>
  );
}

export default ShadowDiscovery;
