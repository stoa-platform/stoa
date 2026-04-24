/**
 * Single-source-of-truth regression lock: apiService.{set,clear}AuthToken
 * must NOT mutate httpClient.defaults.headers. The request interceptor reads
 * getAuthToken() per request — dual-write is the removed P0-9 bug.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { apiService } from './api';
import { httpClient } from './http';

beforeEach(() => {
  delete httpClient.defaults.headers.common['Authorization'];
  apiService.clearAuthToken();
});

afterEach(() => {
  delete httpClient.defaults.headers.common['Authorization'];
  apiService.clearAuthToken();
});

describe('apiService auth token — P0-9 dual-write regression lock', () => {
  it('setAuthToken does not mutate httpClient.defaults.headers.common.Authorization', () => {
    apiService.setAuthToken('token-A');
    expect(apiService.getAuthToken()).toBe('token-A');
    expect(httpClient.defaults.headers.common['Authorization']).toBeUndefined();
  });

  it('clearAuthToken does not touch httpClient.defaults.headers.common.Authorization', () => {
    // Seed the default header to ensure clearAuthToken() does not touch it.
    httpClient.defaults.headers.common['Authorization'] = 'Bearer seeded';
    apiService.setAuthToken('token-A');
    apiService.clearAuthToken();
    expect(apiService.getAuthToken()).toBeNull();
    // Pre-existing header on defaults.headers is preserved — auth façade
    // stays out of this field.
    expect(httpClient.defaults.headers.common['Authorization']).toBe('Bearer seeded');
  });
});
