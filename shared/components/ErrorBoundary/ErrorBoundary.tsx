import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, Home, LogIn, RefreshCw } from 'lucide-react';
import { getFriendlyError } from '../../utils/errorMessages';

// ---- ErrorFallback (default UI) ----

interface ErrorFallbackProps {
  error?: Error;
  resetError?: () => void;
  title?: string;
  description?: string;
}

/**
 * Fallback UI displayed when an error is caught by ErrorBoundary.
 * Shows user-friendly message with retry and home navigation options.
 *
 * CAB-1625: Prevents blank pages when lazy-loaded chunks fail.
 * CAB-1629: Uses getFriendlyError — no raw HTTP status codes.
 */
export function ErrorFallback({
  error,
  resetError,
  title = 'Something went wrong',
  description = 'We encountered an unexpected error. Please try again or go back to the home page.',
}: ErrorFallbackProps) {
  const friendly = error ? getFriendlyError(error) : null;

  const isChunkError =
    error?.name === 'ChunkLoadError' ||
    error?.message?.includes('Loading chunk') ||
    error?.message?.includes('Failed to fetch dynamically imported module');

  const handleRetry = () => {
    if (isChunkError) {
      // ChunkLoadError: full reload to fetch fresh chunks after deployment
      window.location.reload();
      return;
    }
    if (resetError) {
      resetError();
    } else {
      window.location.reload();
    }
  };

  const handleGoHome = () => {
    // Navigate to home — use direct location change since we may be outside Router context
    window.location.href = '/';
  };

  const handleLogin = () => {
    window.location.reload();
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
      <div className="bg-red-50 dark:bg-red-900/20 rounded-full p-4 mb-4">
        <AlertTriangle className="h-12 w-12 text-red-500" />
      </div>

      <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
        {isChunkError ? 'Application Updated' : title}
      </h2>

      <p className="text-neutral-600 dark:text-neutral-400 text-center mb-6 max-w-md">
        {isChunkError
          ? 'A new version is available. Please reload the page.'
          : friendly
            ? friendly.message
            : description}
      </p>

      <div className="flex gap-3">
        {friendly?.action === 'login' ? (
          <button
            onClick={handleLogin}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <LogIn className="h-4 w-4" />
            Log In Again
          </button>
        ) : (
          <button
            onClick={handleRetry}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            {isChunkError ? 'Reload' : 'Try Again'}
          </button>
        )}

        {!isChunkError && (
          <button
            onClick={handleGoHome}
            className="flex items-center gap-2 px-4 py-2 bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-300 dark:hover:bg-neutral-600 transition-colors"
          >
            <Home className="h-4 w-4" />
            Go Home
          </button>
        )}
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

// ---- ErrorBoundary (class component) ----

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

/**
 * Error Boundary component that catches JavaScript errors anywhere in the
 * child component tree and displays a fallback UI instead of crashing.
 *
 * Handles ChunkLoadError (lazy load failures after deployment) gracefully.
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary onError={(e, info) => captureException(e)}>
 *   <Suspense fallback={<PageLoader />}>
 *     <Routes>...</Routes>
 *   </Suspense>
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary] Caught error:', error);
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack);
    this.props.onError?.(error, errorInfo);
  }

  resetError = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return <ErrorFallback error={this.state.error} resetError={this.resetError} />;
    }

    return this.props.children;
  }
}
