/**
 * STOA Developer Portal - MCP Gateway Client
 *
 * Axios instance for MCP Gateway API calls.
 * Used for AI agent tool discovery and invocation.
 *
 * The MCP Gateway exposes platform operations as Model Context Protocol tools,
 * enabling AI agents to manage the STOA platform programmatically.
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import { config } from '../config';
import { getAccessToken } from './api';

// Create axios instance for MCP Gateway
export const mcpClient: AxiosInstance = axios.create({
  baseURL: config.mcp.baseUrl,
  timeout: config.mcp.timeout,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - adds Authorization header
mcpClient.interceptors.request.use(
  (reqConfig) => {
    const token = getAccessToken();
    if (token) {
      reqConfig.headers.Authorization = `Bearer ${token}`;
    }
    return reqConfig;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle errors
mcpClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      switch (error.response.status) {
        case 401:
          console.warn('MCP: Unauthorized - authentication required for tool invocation');
          break;
        case 403:
          console.warn('MCP: Forbidden - insufficient permissions');
          break;
        case 404:
          console.warn('MCP: Tool not found');
          break;
        case 422:
          console.warn('MCP: Invalid tool arguments');
          break;
        default:
          console.error('MCP: Request failed', error.response.status);
      }
    } else if (error.request) {
      console.error('MCP: No response received', error.message);
    } else {
      console.error('MCP: Request setup error', error.message);
    }
    return Promise.reject(error);
  }
);

export default mcpClient;
