import { useState, useCallback } from 'react';
import { AlertTriangle, Copy, Check } from 'lucide-react';

interface ApiKeyRevealDialogProps {
  apiKey: string;
  name: string;
  onClose: () => void;
}

export function ApiKeyRevealDialog({ apiKey, name, onClose }: ApiKeyRevealDialogProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [apiKey]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-lg p-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-2">
          API Key for {name}
        </h3>

        <div className="flex items-start gap-2 p-3 mb-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
          <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 shrink-0 mt-0.5" />
          <p className="text-sm text-yellow-700 dark:text-yellow-300">
            This key will not be shown again. Copy it now and store it securely.
          </p>
        </div>

        <div className="flex items-center gap-2 p-3 bg-neutral-100 dark:bg-neutral-700 rounded-lg font-mono text-sm break-all">
          <span className="flex-1 text-neutral-900 dark:text-white">{apiKey}</span>
          <button
            onClick={handleCopy}
            className="shrink-0 p-1.5 text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 rounded"
            title="Copy to clipboard"
          >
            {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
          </button>
        </div>

        <div className="flex justify-end mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            I&apos;ve copied the key
          </button>
        </div>
      </div>
    </div>
  );
}
