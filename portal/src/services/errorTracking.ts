import { ErrorInfo } from 'react';

interface ErrorPayload {
  message: string;
  stack?: string;
  timestamp: string;
  url: string;
  componentStack?: string | null;
  extra?: Record<string, unknown>;
}

const endpoint = import.meta.env.VITE_ERROR_TRACKING_ENDPOINT as string | undefined;

/**
 * Capture an exception and send to the configured error tracking endpoint.
 * No-op when VITE_ERROR_TRACKING_ENDPOINT is not set.
 * Sentry-compatible payload shape for future migration.
 */
export function captureException(
  error: Error,
  context?: { componentStack?: string | null; extra?: Record<string, unknown> }
): void {
  if (!endpoint) return;

  const payload: ErrorPayload = {
    message: error.message,
    stack: error.stack,
    timestamp: new Date().toISOString(),
    url: window.location.href,
    ...context,
  };

  fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).catch(() => {
    // Silent — error tracking must never break the app
  });
}

/**
 * Convenience wrapper for React ErrorBoundary componentDidCatch.
 */
export function captureErrorBoundary(error: Error, errorInfo: ErrorInfo): void {
  captureException(error, { componentStack: errorInfo.componentStack });
}
