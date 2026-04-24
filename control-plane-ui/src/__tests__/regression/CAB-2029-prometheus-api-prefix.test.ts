import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { usePrometheusQuery, usePrometheusRange } from '../../hooks/usePrometheus';

vi.mock('../../services/http', async () => {
  const actual = await vi.importActual<typeof import('../../services/http')>('../../services/http');
  return {
    ...actual,
    httpClient: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    },
  };
});

const QUERY_RESPONSE = {
  data: {
    status: 'success',
    data: {
      resultType: 'vector',
      result: [{ metric: { name: 'up' }, value: [1234567890, '1'] as [number, string] }],
    },
  },
};

const RANGE_RESPONSE = {
  data: {
    status: 'success',
    data: {
      resultType: 'matrix',
      result: [
        {
          metric: {},
          values: [[1000, '1'] as [number, string], [1010, '2'] as [number, string]],
        },
      ],
    },
  },
};

describe('regression/CAB-2029', () => {
  beforeEach(async () => {
    const { httpClient } = await import('../../services/http');
    (httpClient.get as ReturnType<typeof vi.fn>).mockReset();
  });

  it('keeps Prometheus requests on /v1/metrics/* without an extra /api prefix', async () => {
    const { httpClient } = await import('../../services/http');
    const getMock = httpClient.get as ReturnType<typeof vi.fn>;

    getMock.mockResolvedValueOnce(QUERY_RESPONSE);
    renderHook(() => usePrometheusQuery('up', 0));
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));
    expect(getMock.mock.calls[0][0]).toBe('/v1/metrics/query');
    expect(getMock.mock.calls[0][0]).not.toMatch(/^\/api\//);

    getMock.mockResolvedValueOnce(RANGE_RESPONSE);
    renderHook(() => usePrometheusRange('up', 60, '15s', 0));
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2));
    expect(getMock.mock.calls[1][0]).toBe('/v1/metrics/query_range');
    expect(getMock.mock.calls[1][0]).not.toMatch(/^\/api\//);
  });
});
