// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * STOA Developer Portal - API Client
 *
 * Axios instance with authentication interceptor for Control Plane API calls.
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import { config } from '../config';

// Create axios instance with base configuration
export const apiClient: AxiosInstance = axios.create({
  baseURL: config.api.baseUrl,
  timeout: config.api.timeout,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token storage - will be set by AuthContext
let accessToken: string | null = null;

/**
 * Set the access token for API calls
 * Called by AuthContext when user authenticates
 */
export function setAccessToken(token: string | null) {
  accessToken = token;
}

/**
 * Get the current access token
 */
export function getAccessToken(): string | null {
  return accessToken;
}

// Request interceptor - adds Authorization header
apiClient.interceptors.request.use(
  (config) => {
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - handle errors globally
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Handle specific error cases
    if (error.response) {
      switch (error.response.status) {
        case 401:
          // Token expired or invalid - could trigger re-auth
          console.warn('API: Unauthorized - token may be expired');
          break;
        case 403:
          console.warn('API: Forbidden - insufficient permissions');
          break;
        case 404:
          console.warn('API: Resource not found');
          break;
        case 500:
          console.error('API: Server error');
          break;
        default:
          console.error('API: Request failed', error.response.status);
      }
    } else if (error.request) {
      console.error('API: No response received', error.message);
    } else {
      console.error('API: Request setup error', error.message);
    }
    return Promise.reject(error);
  }
);

export default apiClient;
