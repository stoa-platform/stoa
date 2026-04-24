import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import {
  clearAuthToken,
  drainRefreshQueue,
  enqueueRefresh,
  getIsRefreshing,
  getTokenRefresher,
  setAuthToken,
  setIsRefreshing,
  type TokenRefresher,
} from './auth';
import { applyFriendlyErrorMessage } from './errors';
import { config } from '../../config';

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

function currentTimeoutMs(): number {
  const fromConfig = config?.auth?.refreshTimeoutMs;
  return typeof fromConfig === 'number' && fromConfig > 0 ? fromConfig : 30_000;
}

function refreshWithTimeout(refresher: TokenRefresher, timeoutMs?: number): Promise<string | null> {
  const effectiveTimeout = timeoutMs ?? currentTimeoutMs();
  let timer: ReturnType<typeof setTimeout> | undefined;

  const timeoutPromise = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`Token refresh timeout after ${effectiveTimeout}ms`)),
      effectiveTimeout
    );
  });

  return Promise.race([refresher(), timeoutPromise]).finally(() => {
    if (timer !== undefined) clearTimeout(timer);
  });
}

/**
 * Trigger a token refresh, respecting the single-flight queue.
 * - If a refresh is already in flight, waits on the shared queue (coalesced).
 * - On success: sets the new token, drains the queue with it, returns the token.
 * - On null from refresher: clears auth, rejects queued requests, throws.
 * - On refresher error / timeout: clears auth, rejects queued requests, throws.
 * - If no refresher is registered: returns null without side effects.
 *
 * Reused by the SSE layer (services/http/sse.ts) for active refresh on 401.
 */
export async function refreshAuthTokenWithTimeout(): Promise<string | null> {
  const refresher = getTokenRefresher();
  if (!refresher) return null;

  if (getIsRefreshing()) {
    return new Promise<string | null>((resolve, reject) => {
      enqueueRefresh({ resolve, reject });
    });
  }

  setIsRefreshing(true);
  try {
    const newToken = await refreshWithTimeout(refresher);
    if (newToken) {
      setAuthToken(newToken);
      drainRefreshQueue({ resolveWith: newToken });
      return newToken;
    }
    clearAuthToken();
    const err = new Error('Token refresh returned null — session expired');
    drainRefreshQueue({ rejectWith: err });
    throw err;
  } catch (err) {
    clearAuthToken();
    drainRefreshQueue({ rejectWith: err });
    throw err;
  } finally {
    setIsRefreshing(false);
  }
}

export function installRefreshInterceptor(instance: AxiosInstance): void {
  instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const originalRequest = error.config as RetriableConfig | undefined;
      const tokenRefresher = getTokenRefresher();

      if (
        error.response?.status === 401 &&
        originalRequest &&
        !originalRequest._retry &&
        tokenRefresher
      ) {
        originalRequest._retry = true;

        try {
          const newToken = await refreshAuthTokenWithTimeout();
          if (newToken) {
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
            }
            return instance(originalRequest);
          }
          // newToken === null: no refresher registered (should not happen here
          // because we checked above, but guard for race conditions).
          return Promise.reject(error);
        } catch (refreshError) {
          return Promise.reject(refreshError);
        }
      }

      applyFriendlyErrorMessage(error);
      return Promise.reject(error);
    }
  );
}
