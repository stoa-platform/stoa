/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Must mock before import so module-level code uses mocked axios
vi.mock('axios', () => {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  };
  const instance = {
    interceptors,
    get: vi.fn(),
    post: vi.fn(),
    defaults: { headers: { common: {} } },
  };
  return {
    default: {
      create: vi.fn(() => instance),
    },
  };
});

vi.mock('../config', () => ({
  config: {
    api: { baseUrl: 'https://api.test.dev', timeout: 5000 },
  },
}));

import { setAccessToken, getAccessToken, apiClient } from './api';
import axios from 'axios';

// Capture interceptor handlers registered at module init (before clearAllMocks wipes them)
const requestHandler = vi.mocked(apiClient.interceptors.request.use).mock.calls[0][0] as any;
const requestErrorHandler = vi.mocked(apiClient.interceptors.request.use).mock.calls[0][1] as any;
const responseHandler = vi.mocked(apiClient.interceptors.response.use).mock.calls[0][0] as any;
const responseErrorHandler = vi.mocked(apiClient.interceptors.response.use).mock.calls[0][1] as any;

describe('api module', () => {
  beforeEach(() => {
    setAccessToken(null);
  });

  describe('token management', () => {
    it('should start with null token', () => {
      expect(getAccessToken()).toBeNull();
    });

    it('should set and get access token', () => {
      setAccessToken('test-token-123');
      expect(getAccessToken()).toBe('test-token-123');
    });

    it('should clear token when set to null', () => {
      setAccessToken('token');
      setAccessToken(null);
      expect(getAccessToken()).toBeNull();
    });
  });

  describe('axios instance creation', () => {
    it('should create axios instance with config', () => {
      expect(axios.create).toHaveBeenCalledWith({
        baseURL: 'https://api.test.dev',
        timeout: 5000,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    it('should have registered interceptor handlers', () => {
      expect(requestHandler).toBeDefined();
      expect(responseHandler).toBeDefined();
      expect(responseErrorHandler).toBeDefined();
    });
  });

  describe('request interceptor', () => {
    it('should add Authorization header when token is set', () => {
      setAccessToken('bearer-token');
      const config = { headers: {} as any };
      const result = requestHandler(config);
      expect(result.headers.Authorization).toBe('Bearer bearer-token');
    });

    it('should not add Authorization header when token is null', () => {
      setAccessToken(null);
      const config = { headers: {} as any };
      const result = requestHandler(config);
      expect(result.headers.Authorization).toBeUndefined();
    });

    it('should reject on request error', async () => {
      const error = new Error('Request setup failed');
      await expect(requestErrorHandler(error)).rejects.toThrow('Request setup failed');
    });
  });

  describe('response interceptor', () => {
    it('should pass through successful responses', () => {
      const response = { status: 200, data: { ok: true } };
      expect(responseHandler(response)).toEqual(response);
    });

    it('should reject and log on 401 error', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const error = { response: { status: 401 }, message: 'Unauthorized' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('API: Unauthorized - token may be expired');
      consoleSpy.mockRestore();
    });

    it('should reject and log on 403 error', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const error = { response: { status: 403 }, message: 'Forbidden' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('API: Forbidden - insufficient permissions');
      consoleSpy.mockRestore();
    });

    it('should reject and log on 404 error', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const error = { response: { status: 404 }, message: 'Not found' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('API: Resource not found');
      consoleSpy.mockRestore();
    });

    it('should reject and log on 500 error', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const error = { response: { status: 500 }, message: 'Server error' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('API: Server error');
      consoleSpy.mockRestore();
    });

    it('should handle network errors (no response)', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const error = { request: {}, message: 'Network Error' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('API: No response received', 'Network Error');
      consoleSpy.mockRestore();
    });

    it('should handle request setup errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const error = { message: 'Invalid URL' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('API: Request setup error', 'Invalid URL');
      consoleSpy.mockRestore();
    });

    it('should handle default error status codes', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const error = { response: { status: 502 }, message: 'Bad Gateway' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('API: Request failed', 502);
      consoleSpy.mockRestore();
    });
  });
});
