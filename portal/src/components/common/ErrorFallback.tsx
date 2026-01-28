// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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
      <div className="bg-red-50 rounded-full p-4 mb-4">
        <AlertTriangle className="h-12 w-12 text-red-500" />
      </div>

      {/* Title */}
      <h2 className="text-xl font-semibold text-gray-900 mb-2">{title}</h2>

      {/* Description */}
      <p className="text-gray-600 text-center mb-6 max-w-md">{description}</p>

      {/* Error details (development only or for debugging) */}
      {error && (
        <div className="bg-gray-100 p-4 rounded-lg mb-6 max-w-lg w-full">
          <p className="text-sm font-medium text-gray-700 mb-2">Error details:</p>
          <pre className="text-sm text-gray-600 overflow-auto whitespace-pre-wrap break-words">
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
          className="flex items-center gap-2 px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
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
      <p className="text-sm text-gray-600 mb-3">{message}</p>
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
