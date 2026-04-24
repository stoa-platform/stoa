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

import { monitoringClient } from './monitoring';

describe('monitoringClient.listTransactions (P1-14 — != null keeps 0)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHttpClient.get.mockResolvedValue({ data: { transactions: [] } });
  });

  it('forwards statusCode=0 in the params (regression guard)', async () => {
    await monitoringClient.listTransactions(20, undefined, undefined, undefined, 0);

    const [, opts] = mockHttpClient.get.mock.calls[0];
    // The prior `if (statusCode)` pattern silently dropped 0 because JS
    // coerces it to falsy. We now use `!= null`, so 0 must reach the wire.
    expect(opts.params.status_code).toBe(0);
  });

  it('omits statusCode when undefined', async () => {
    await monitoringClient.listTransactions(20);

    const [, opts] = mockHttpClient.get.mock.calls[0];
    expect('status_code' in opts.params).toBe(false);
  });

  it('keeps the provided limit, status, and route together', async () => {
    await monitoringClient.listTransactions(50, '500', '1h', 'mcp', 404, '/api/foo');

    const [, opts] = mockHttpClient.get.mock.calls[0];
    expect(opts.params).toMatchObject({
      limit: 50,
      status: '500',
      time_range: '1h',
      service_type: 'mcp',
      status_code: 404,
      route: '/api/foo',
    });
  });
});
