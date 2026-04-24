import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockHttpClient } = vi.hoisted(() => ({
  mockHttpClient: {
    get: vi.fn(),
  },
}));

vi.mock('../http', async () => {
  const actual = await vi.importActual<typeof import('../http')>('../http');
  return { ...actual, httpClient: mockHttpClient };
});

import { chatClient } from './chat';

describe('chatClient.getUsageBySource (P1-13 — spread default guard)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHttpClient.get.mockResolvedValue({ data: {} });
  });

  it('uses source default when caller passes { group_by: undefined }', async () => {
    await chatClient.getUsageBySource('tenant-1', { group_by: undefined, days: 7 });

    expect(mockHttpClient.get).toHaveBeenCalledTimes(1);
    const [url, opts] = mockHttpClient.get.mock.calls[0];
    expect(url).toContain('/chat/usage/tenant');
    // The default must win when group_by is undefined, so the backend
    // receives the client's intended `source` grouping rather than the
    // backend-side fallback.
    expect(opts.params).toEqual({ group_by: 'source', days: 7 });
  });

  it('honors explicit group_by when provided', async () => {
    await chatClient.getUsageBySource('tenant-1', { group_by: 'model' });

    const [, opts] = mockHttpClient.get.mock.calls[0];
    expect(opts.params.group_by).toBe('model');
  });

  it('uses source default when called with no params', async () => {
    await chatClient.getUsageBySource('tenant-1');

    const [, opts] = mockHttpClient.get.mock.calls[0];
    expect(opts.params.group_by).toBe('source');
  });
});
