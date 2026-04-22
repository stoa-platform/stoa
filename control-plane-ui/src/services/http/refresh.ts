import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import {
  drainRefreshQueue,
  enqueueRefresh,
  getIsRefreshing,
  getTokenRefresher,
  setAuthToken,
  setIsRefreshing,
} from './auth';
import { applyFriendlyErrorMessage } from './errors';

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

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
        if (getIsRefreshing()) {
          return new Promise<string | null>((resolve, reject) => {
            enqueueRefresh({ resolve, reject });
          }).then((token) => {
            if (token && originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${token}`;
            }
            return instance(originalRequest);
          });
        }

        originalRequest._retry = true;
        setIsRefreshing(true);

        try {
          const newToken = await tokenRefresher();
          if (newToken) {
            setAuthToken(newToken);
            drainRefreshQueue({ resolveWith: newToken });
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
            }
            return instance(originalRequest);
          }
          // Token refresh returned null — session expired, reject queued requests
          drainRefreshQueue({ rejectWith: error });
        } catch (refreshError) {
          drainRefreshQueue({ rejectWith: refreshError });
          return Promise.reject(refreshError);
        } finally {
          setIsRefreshing(false);
        }
      }

      applyFriendlyErrorMessage(error);
      return Promise.reject(error);
    }
  );
}
