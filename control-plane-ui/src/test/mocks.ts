// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { vi } from 'vitest';
import type { MCPTool, ToolSubscription, ToolUsageSummary } from '../types';

// Mock tool data
export const mockTool: MCPTool = {
  name: 'stoa_list_apis',
  description: 'List all APIs in the STOA platform',
  inputSchema: {
    type: 'object',
    properties: {
      tenant_id: {
        type: 'string',
        description: 'Filter by tenant ID',
      },
      status: {
        type: 'string',
        enum: ['draft', 'published', 'deprecated'],
        description: 'Filter by status',
      },
      limit: {
        type: 'integer',
        default: 20,
        description: 'Maximum number of results',
      },
    },
    required: ['tenant_id'],
  },
  method: 'GET',
  tags: ['platform', 'apis'],
  version: '1.0.0',
  tenantId: 'acme-corp',
  endpoint: 'https://api.gostoa.dev/v1/apis',
};

export const mockTools: MCPTool[] = [
  mockTool,
  {
    name: 'stoa_get_api',
    description: 'Get details of a specific API',
    inputSchema: {
      type: 'object',
      properties: {
        api_id: {
          type: 'string',
          description: 'The API identifier',
        },
      },
      required: ['api_id'],
    },
    method: 'GET',
    tags: ['platform', 'apis'],
    version: '1.0.0',
  },
  {
    name: 'stoa_search_payments',
    description: 'Search payment records by various criteria',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query',
        },
      },
      required: ['query'],
    },
    method: 'POST',
    tags: ['payments', 'search'],
    version: '1.0.0',
    tenantId: 'acme-corp',
  },
];

export const mockSubscription: ToolSubscription = {
  id: 'sub-123',
  userId: 'user-456',
  toolName: 'stoa_list_apis',
  subscribedAt: '2024-01-15T10:30:00Z',
  status: 'active',
  usageCount: 42,
};

export const mockUsageSummary: ToolUsageSummary = {
  period: 'week',
  startDate: '2024-01-08',
  endDate: '2024-01-15',
  totalCalls: 156,
  successRate: 0.98,
  totalCostUnits: 0.0234,
  avgLatencyMs: 145,
  toolBreakdown: [
    {
      toolName: 'stoa_list_apis',
      totalCalls: 100,
      successCount: 98,
      errorCount: 2,
      avgLatencyMs: 120,
      totalCostUnits: 0.015,
    },
    {
      toolName: 'stoa_get_api',
      totalCalls: 56,
      successCount: 55,
      errorCount: 1,
      avgLatencyMs: 180,
      totalCostUnits: 0.0084,
    },
  ],
};

// Mock MCP Gateway service
export const mockMcpGatewayService = {
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  getTools: vi.fn().mockResolvedValue({ tools: mockTools, totalCount: mockTools.length }),
  getTool: vi.fn().mockResolvedValue(mockTool),
  getToolSchema: vi.fn().mockResolvedValue({ name: mockTool.name, inputSchema: mockTool.inputSchema }),
  getToolTags: vi.fn().mockResolvedValue(['platform', 'apis', 'payments', 'search']),
  getMySubscriptions: vi.fn().mockResolvedValue([mockSubscription]),
  subscribeTool: vi.fn().mockResolvedValue(mockSubscription),
  unsubscribeTool: vi.fn().mockResolvedValue(undefined),
  updateSubscription: vi.fn().mockResolvedValue(mockSubscription),
  getMyUsage: vi.fn().mockResolvedValue(mockUsageSummary),
  getToolUsage: vi.fn().mockResolvedValue(mockUsageSummary),
  getUsageHistory: vi.fn().mockResolvedValue({ dataPoints: [] }),
  getServerInfo: vi.fn().mockResolvedValue({
    name: 'STOA MCP Gateway',
    version: '1.0.0',
    protocolVersion: '1.0',
    capabilities: { tools: true, resources: true, prompts: true },
  }),
  healthCheck: vi.fn().mockResolvedValue({ status: 'healthy' }),
};
