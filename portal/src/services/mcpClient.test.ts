/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, vi } from 'vitest';

vi.mock('axios', () => {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  };
  const instance = {
    interceptors,
    get: vi.fn(),
    post: vi.fn(),
  };
  return {
    default: {
      create: vi.fn(() => instance),
    },
  };
});

vi.mock('../config', () => ({
  config: {
    mcp: { baseUrl: 'https://mcp.test.dev', timeout: 30000 },
  },
}));

let mockToken: string | null = null;
vi.mock('./api', () => ({
  getAccessToken: () => mockToken,
}));

import { mcpClient } from './mcpClient';
import axios from 'axios';

// Capture interceptor handlers registered at module init
const requestHandler = vi.mocked(mcpClient.interceptors.request.use).mock.calls[0][0] as any;
const responseHandler = vi.mocked(mcpClient.interceptors.response.use).mock.calls[0][0] as any;
const responseErrorHandler = vi.mocked(mcpClient.interceptors.response.use).mock.calls[0][1] as any;

describe('mcpClient module', () => {
  describe('axios instance creation', () => {
    it('should create MCP axios instance with config', () => {
      expect(axios.create).toHaveBeenCalledWith({
        baseURL: 'https://mcp.test.dev',
        timeout: 30000,
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
    it('should add Authorization header when token exists', () => {
      mockToken = 'mcp-token';
      const config = { headers: {} as any };
      const result = requestHandler(config);
      expect(result.headers.Authorization).toBe('Bearer mcp-token');
    });

    it('should not add header when token is null', () => {
      mockToken = null;
      const config = { headers: {} as any };
      const result = requestHandler(config);
      expect(result.headers.Authorization).toBeUndefined();
    });
  });

  describe('response interceptor', () => {
    it('should pass through successful responses', () => {
      const response = { status: 200, data: { tools: [] } };
      expect(responseHandler(response)).toEqual(response);
    });

    it('should log warning on 422 (invalid tool args)', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const error = { response: { status: 422 }, message: 'Unprocessable' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('MCP: Invalid tool arguments');
      consoleSpy.mockRestore();
    });

    it('should log warning on 401', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const error = { response: { status: 401 }, message: 'Unauthorized' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith(
        'MCP: Unauthorized - authentication required for tool invocation'
      );
      consoleSpy.mockRestore();
    });

    it('should log warning on 404 (tool not found)', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const error = { response: { status: 404 }, message: 'Not found' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('MCP: Tool not found');
      consoleSpy.mockRestore();
    });

    it('should handle network errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const error = { request: {}, message: 'timeout' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('MCP: No response received', 'timeout');
      consoleSpy.mockRestore();
    });

    it('should handle request setup errors', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const error = { message: 'Invalid config' };

      await expect(responseErrorHandler(error)).rejects.toEqual(error);
      expect(consoleSpy).toHaveBeenCalledWith('MCP: Request setup error', 'Invalid config');
      consoleSpy.mockRestore();
    });
  });
});
