import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import { getAuthToken } from './auth';
import { applyFriendlyErrorMessage } from './errors';

export function installRequestInterceptor(instance: AxiosInstance): void {
  instance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = getAuthToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error) => {
      // P2-1: mirror response interceptor's friendly-error decoration on
      // the (rare) pre-send failure path (e.g., request transformer throw).
      // Guarded on AxiosError to avoid touching unrelated throws.
      if (axios.isAxiosError(error)) {
        applyFriendlyErrorMessage(error);
      }
      return Promise.reject(error);
    }
  );
}
