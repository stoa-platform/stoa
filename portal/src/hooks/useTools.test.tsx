import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useTools,
  useTool,
  useToolsByTag,
  useToolTags,
  useToolCategories,
  useToolCategoriesWithCounts,
  useSearchTools,
  useToolsByCategory,
  useToolSchema,
  useSubscribeToTool,
  useMCPServerInfo,
  useInvokeTool,
  useMCPHealth,
} from './useTools';

vi.mock('../services/tools', () => ({
  toolsService: {
    listTools: vi.fn(),
    getTool: vi.fn(),
    getByTag: vi.fn(),
    getTags: vi.fn(),
    getCategories: vi.fn(),
    searchTools: vi.fn(),
    getByCategory: vi.fn(),
    getServerInfo: vi.fn(),
    invokeTool: vi.fn(),
    checkHealth: vi.fn(),
  },
}));

vi.mock('../services/subscriptions', () => ({
  subscriptionsService: {
    createSubscription: vi.fn(),
  },
}));

import { toolsService } from '../services/tools';
import { subscriptionsService } from '../services/subscriptions';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useTools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch tools list', async () => {
    vi.mocked(toolsService.listTools).mockResolvedValueOnce({
      tools: [{ name: 'list-apis' }],
      nextCursor: null,
    } as any);

    const { result } = renderHook(() => useTools(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.tools).toHaveLength(1);
  });

  it('should pass params', async () => {
    vi.mocked(toolsService.listTools).mockResolvedValueOnce({ tools: [] } as any);

    renderHook(() => useTools({ tag: 'finance' }), { wrapper: createWrapper() });
    await waitFor(() => expect(toolsService.listTools).toHaveBeenCalledWith({ tag: 'finance' }));
  });
});

describe('useTool', () => {
  beforeEach(() => vi.clearAllMocks());

  it('should fetch a single tool', async () => {
    vi.mocked(toolsService.getTool).mockResolvedValueOnce({
      name: 'list-apis',
      description: 'List APIs',
    } as any);

    const { result } = renderHook(() => useTool('list-apis'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe('list-apis');
  });

  it('should not fetch when name is undefined', () => {
    const { result } = renderHook(() => useTool(undefined), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useToolsByTag', () => {
  beforeEach(() => vi.clearAllMocks());

  it('should fetch tools by tag', async () => {
    vi.mocked(toolsService.getByTag).mockResolvedValueOnce([{ name: 'tool-1' }] as any);

    const { result } = renderHook(() => useToolsByTag('finance'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });

  it('should not fetch when tag is undefined', () => {
    const { result } = renderHook(() => useToolsByTag(undefined), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useToolTags', () => {
  it('should fetch tags', async () => {
    vi.mocked(toolsService.getTags).mockResolvedValueOnce({
      tags: [{ name: 'finance', count: 3 }],
    } as any);

    const { result } = renderHook(() => useToolTags(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.tags).toHaveLength(1);
  });
});

describe('useToolCategories', () => {
  it('should fetch and map category names', async () => {
    vi.mocked(toolsService.getCategories).mockResolvedValueOnce({
      categories: [
        { name: 'Finance', count: 5 },
        { name: 'Sales', count: 3 },
      ],
    } as any);

    const { result } = renderHook(() => useToolCategories(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(['Finance', 'Sales']);
  });
});

describe('useToolCategoriesWithCounts', () => {
  it('should fetch full category data', async () => {
    vi.mocked(toolsService.getCategories).mockResolvedValueOnce({
      categories: [{ name: 'Finance', count: 5 }],
    } as any);

    const { result } = renderHook(() => useToolCategoriesWithCounts(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.categories).toHaveLength(1);
  });
});

describe('useSearchTools', () => {
  beforeEach(() => vi.clearAllMocks());

  it('should search tools with 2+ chars', async () => {
    vi.mocked(toolsService.searchTools).mockResolvedValueOnce([{ name: 'tool-1' }] as any);

    const { result } = renderHook(() => useSearchTools('pay'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });

  it('should not search with less than 2 chars', () => {
    const { result } = renderHook(() => useSearchTools('p'), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('should not search when query is undefined', () => {
    const { result } = renderHook(() => useSearchTools(undefined), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useToolsByCategory', () => {
  it('should fetch tools by category', async () => {
    vi.mocked(toolsService.getByCategory).mockResolvedValueOnce([{ name: 'tool-1' }] as any);

    const { result } = renderHook(() => useToolsByCategory('Finance'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it('should not fetch when category is undefined', () => {
    const { result } = renderHook(() => useToolsByCategory(undefined), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useToolSchema', () => {
  it('should return inputSchema from tool data', async () => {
    vi.mocked(toolsService.getTool).mockResolvedValueOnce({
      name: 'list-apis',
      inputSchema: { type: 'object', properties: { limit: { type: 'number' } } },
    } as any);

    const { result } = renderHook(() => useToolSchema('list-apis'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.type).toBe('object');
  });
});

describe('useSubscribeToTool', () => {
  beforeEach(() => vi.clearAllMocks());

  it('should subscribe to a tool', async () => {
    vi.mocked(subscriptionsService.createSubscription).mockResolvedValueOnce({
      subscription: { id: 'sub-1' },
      api_key: 'sk_test',
    } as any);

    const { result } = renderHook(() => useSubscribeToTool(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate({ toolId: 'tool-1', plan: 'free' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.api_key).toBe('sk_test');
  });
});

describe('useMCPServerInfo', () => {
  it('should fetch server info', async () => {
    vi.mocked(toolsService.getServerInfo).mockResolvedValueOnce({
      name: 'stoa-gateway',
      version: '1.0',
    } as any);

    const { result } = renderHook(() => useMCPServerInfo(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe('stoa-gateway');
  });
});

describe('useInvokeTool', () => {
  it('should invoke a tool', async () => {
    vi.mocked(toolsService.invokeTool).mockResolvedValueOnce({
      content: [{ type: 'text', text: 'result' }],
    } as any);

    const { result } = renderHook(() => useInvokeTool(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate({ name: 'list-apis', args: { limit: 10 } });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(toolsService.invokeTool).toHaveBeenCalledWith('list-apis', { limit: 10 });
  });
});

describe('useMCPHealth', () => {
  it('should fetch MCP health', async () => {
    vi.mocked(toolsService.checkHealth).mockResolvedValueOnce({ status: 'ok' });

    const { result } = renderHook(() => useMCPHealth(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe('ok');
  });
});
