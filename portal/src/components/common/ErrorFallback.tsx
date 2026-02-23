import { AlertTriangle, Home, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface ErrorFallbackProps {
  error?: Error;
  resetError?: () => void;
  title?: string;
  description?: string;
}

/**
 * Fallback UI displayed when an error is caught by ErrorBoundary.
 * Shows error message with retry and home navigation options.
 */
export function ErrorFallback({
  error,
  resetError,
  title = 'Something went wrong',
  description = 'We encountered an unexpected error. Please try again or go back to the home page.',
}: ErrorFallbackProps) {
  const navigate = useNavigate();

  const handleRetry = () => {
    if (resetError) {
      resetError();
    } else {
      window.location.reload();
    }
  };

  const handleGoHome = () => {
    // Reset error state if available before navigating
    resetError?.();
    navigate('/');
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
      {/* Error icon */}
      <div className="bg-red-50 dark:bg-red-900/20 rounded-full p-4 mb-4">
        <AlertTriangle className="h-12 w-12 text-red-500" />
      </div>

      {/* Title */}
      <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">{title}</h2>

      {/* Description */}
      <p className="text-neutral-600 dark:text-neutral-400 text-center mb-6 max-w-md">{description}</p>

      {/* Error details (development only or for debugging) */}
      {error && (
        <div className="bg-neutral-100 dark:bg-neutral-700 p-4 rounded-lg mb-6 max-w-lg w-full">
          <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            Error details:
          </p>
          <pre className="text-sm text-neutral-600 dark:text-neutral-400 overflow-auto whitespace-pre-wrap break-words">
            {error.message}
          </pre>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleRetry}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Try Again
        </button>

        <button
          onClick={handleGoHome}
          className="flex items-center gap-2 px-4 py-2 bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-300 dark:hover:bg-neutral-600 transition-colors"
        >
          <Home className="h-4 w-4" />
          Go Home
        </button>
      </div>
    </div>
  );
}

/**
 * Compact error fallback for use in smaller components/cards.
 */
export function CompactErrorFallback({
  resetError,
  message = 'Failed to load',
}: {
  error?: Error;
  resetError?: () => void;
  message?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center p-6 text-center">
      <AlertTriangle className="h-8 w-8 text-red-500 mb-2" />
      <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-3">{message}</p>
      {resetError && (
        <button
          onClick={resetError}
          className="text-sm text-primary-600 hover:text-primary-700 flex items-center gap-1"
        >
          <RefreshCw className="h-3 w-3" />
          Retry
        </button>
      )}
    </div>
  );
}
