/**
 * User-friendly error message mapper for API errors.
 *
 * Converts raw Axios/HTTP error messages (e.g. "Request failed with status code 401")
 * into human-readable messages suitable for display in UI components.
 *
 * CAB-1629: No raw HTTP status codes visible in any error UI component.
 */

export interface FriendlyError {
  /** User-facing message */
  message: string;
  /** Suggested call-to-action type */
  action?: 'retry' | 'login' | 'home' | 'none';
}

const STATUS_MESSAGES: Record<number, FriendlyError> = {
  400: { message: 'The request was invalid. Please check your input and try again.', action: 'retry' },
  401: { message: 'Your session has expired. Please log in again.', action: 'login' },
  403: { message: "You don't have permission to access this resource.", action: 'home' },
  404: { message: 'The requested resource was not found.', action: 'home' },
  408: { message: 'The request timed out. Please try again.', action: 'retry' },
  409: { message: 'A conflict occurred. The resource may have been modified. Please refresh and try again.', action: 'retry' },
  422: { message: 'The provided data is invalid. Please check your input.', action: 'retry' },
  429: { message: 'Too many requests. Please wait a moment and try again.', action: 'retry' },
  500: { message: 'Something went wrong on our end. Please try again later.', action: 'retry' },
  502: { message: 'The server is temporarily unavailable. Please try again later.', action: 'retry' },
  503: { message: 'The service is temporarily unavailable. Please try again later.', action: 'retry' },
  504: { message: 'The server took too long to respond. Please try again.', action: 'retry' },
};

const NETWORK_ERROR: FriendlyError = {
  message: 'Unable to connect to the server. Please check your connection.',
  action: 'retry',
};

const GENERIC_ERROR: FriendlyError = {
  message: 'Something went wrong. Please try again later.',
  action: 'retry',
};

/**
 * Pattern matching raw Axios error messages like "Request failed with status code 401"
 */
const RAW_STATUS_PATTERN = /Request failed with status code (\d{3})/;

/**
 * Extracts the HTTP status code from an error object.
 * Handles Axios errors (error.response.status) and raw message strings.
 */
function extractStatusCode(error: unknown): number | null {
  if (error && typeof error === 'object') {
    // AxiosError shape: error.response.status
    const axiosError = error as { response?: { status?: number }; message?: string };
    if (axiosError.response?.status) {
      return axiosError.response.status;
    }
    // Check message for raw status code pattern
    if (axiosError.message) {
      const match = axiosError.message.match(RAW_STATUS_PATTERN);
      if (match) {
        return parseInt(match[1], 10);
      }
    }
  }
  // String error message
  if (typeof error === 'string') {
    const match = error.match(RAW_STATUS_PATTERN);
    if (match) {
      return parseInt(match[1], 10);
    }
  }
  return null;
}

/**
 * Checks if an error is a network error (no response received).
 */
function isNetworkError(error: unknown): boolean {
  if (error && typeof error === 'object') {
    const axiosError = error as { request?: unknown; response?: unknown; message?: string; code?: string };
    // Axios sets error.request without error.response for network errors
    if (axiosError.request && !axiosError.response) {
      return true;
    }
    // Check common network error codes
    if (axiosError.code === 'ERR_NETWORK' || axiosError.code === 'ECONNABORTED') {
      return true;
    }
    // Check message patterns
    if (axiosError.message === 'Network Error') {
      return true;
    }
  }
  if (typeof error === 'string') {
    return error === 'Network Error' || error.includes('Unable to connect');
  }
  return false;
}

/**
 * Converts any error into a user-friendly error message.
 *
 * Priority:
 * 1. Network error detection
 * 2. HTTP status code mapping (from response or message pattern)
 * 3. Backend detail message (error.response.data.detail) — if not a raw status code
 * 4. Generic fallback
 *
 * @param error - Any error (AxiosError, Error, string, unknown)
 * @param fallback - Optional custom fallback message
 * @returns User-friendly error object
 */
export function getFriendlyError(error: unknown, fallback?: string): FriendlyError {
  // 1. Network errors
  if (isNetworkError(error)) {
    return NETWORK_ERROR;
  }

  // 2. Extract status code and map
  const statusCode = extractStatusCode(error);
  if (statusCode && STATUS_MESSAGES[statusCode]) {
    return STATUS_MESSAGES[statusCode];
  }

  // 3. Check for backend detail message (FastAPI sends `detail` in response body)
  if (error && typeof error === 'object') {
    const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
    const detail = axiosError.response?.data?.detail;
    if (detail && typeof detail === 'string' && !RAW_STATUS_PATTERN.test(detail)) {
      return { message: detail, action: 'retry' };
    }
  }

  // 4. Fallback
  if (fallback) {
    return { message: fallback, action: 'retry' };
  }

  return GENERIC_ERROR;
}

/**
 * Convenience: returns just the user-friendly message string.
 *
 * @param error - Any error
 * @param fallback - Optional custom fallback message
 * @returns User-friendly message string
 */
export function getFriendlyErrorMessage(error: unknown, fallback?: string): string {
  return getFriendlyError(error, fallback).message;
}
