import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { scalarValue, groupByLabel, usePrometheusQuery, usePrometheusRange } from './usePrometheus';

// P0-7 regression lock: hooks must route through httpClient so that
// the refresh interceptor sees Prometheus 401s. Mock the shared
// httpClient instance — any reversion to fetch() will fail these tests.
vi.mock('../services/http', async () => {
  const actual = await vi.importActual<typeof import('../services/http')>('../services/http');
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

const PROM_RESPONSE = {
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

describe('usePrometheus hooks — P0-7 regression lock', () => {
  beforeEach(async () => {
    const { httpClient } = await import('../services/http');
    (httpClient.get as ReturnType<typeof vi.fn>).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('usePrometheusQuery calls httpClient.get, not fetch()', async () => {
    const { httpClient } = await import('../services/http');
    (httpClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(PROM_RESPONSE);

    renderHook(() => usePrometheusQuery('up', 0));

    await waitFor(() => {
      expect(httpClient.get).toHaveBeenCalled();
    });
    const [url, opts] = (httpClient.get as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/v1/metrics/query');
    expect(opts).toMatchObject({ params: { query: 'up' }, timeout: 10_000 });
  });

  // regression for double /api/v1/... prefix against api.gostoa.dev (reported 2026-04-24).
  // httpClient baseURL already points at the cp-api host, so the path must start with /v1 — never /api/v1.
  it('usePrometheus URLs do not carry an /api prefix (prod regression)', async () => {
    const { httpClient } = await import('../services/http');
    const getMock = httpClient.get as ReturnType<typeof vi.fn>;
    getMock.mockResolvedValue(PROM_RESPONSE);

    renderHook(() => usePrometheusQuery('up', 0));
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(getMock.mock.calls[0][0]).not.toMatch(/^\/api\//);

    getMock.mockReset();
    getMock.mockResolvedValue(RANGE_RESPONSE);
    renderHook(() => usePrometheusRange('up', 60, '15s', 0));
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(getMock.mock.calls[0][0]).not.toMatch(/^\/api\//);
  });

  it('usePrometheusRange calls httpClient.get with correct params', async () => {
    const { httpClient } = await import('../services/http');
    (httpClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(RANGE_RESPONSE);

    renderHook(() => usePrometheusRange('up', 60, '15s', 0));

    await waitFor(() => {
      expect(httpClient.get).toHaveBeenCalled();
    });
    const [url, opts] = (httpClient.get as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/v1/metrics/query_range');
    expect(opts.params).toMatchObject({ query: 'up', step: '15s' });
    expect(typeof opts.params.start).toBe('number');
    expect(typeof opts.params.end).toBe('number');
    expect(opts.timeout).toBe(10_000);
  });

  it('usePrometheusQuery surfaces axios error (refresh path is exercised by the shared interceptor)', async () => {
    const { httpClient } = await import('../services/http');
    (httpClient.get as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Request failed with status code 401')
    );

    const { result } = renderHook(() => usePrometheusQuery('up', 0));

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });
    // The hook does not retry; the shared httpClient interceptor handles 401
    // transparently. On a real 401, httpClient.get would resolve with retried
    // response. This test just locks that no extra logic bypasses it.
    expect(result.current.data).toBeNull();
  });

  it('usePrometheus timeout goes through axios not AbortSignal', async () => {
    const { httpClient } = await import('../services/http');
    (httpClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(PROM_RESPONSE);

    renderHook(() => usePrometheusQuery('up', 0));

    await waitFor(() => {
      expect(httpClient.get).toHaveBeenCalled();
    });
    const [, opts] = (httpClient.get as ReturnType<typeof vi.fn>).mock.calls[0];
    // Axios timeout (number, ms), not an AbortSignal.
    expect(opts.timeout).toBe(10_000);
    expect(opts.signal).toBeUndefined();
  });
});

// Only test the pure utility functions - hook testing is complex with async/intervals
// The hooks are tested indirectly via the dashboard component tests

describe('scalarValue', () => {
  it('returns null for null input', () => {
    expect(scalarValue(null)).toBeNull();
  });

  it('returns null for empty array', () => {
    expect(scalarValue([])).toBeNull();
  });

  it('returns null when value is undefined', () => {
    expect(scalarValue([{ metric: {}, value: undefined }])).toBeNull();
  });

  it('returns null when value cannot be parsed', () => {
    expect(scalarValue([{ metric: {}, value: [123, 'invalid'] }])).toBeNull();
  });

  it('extracts scalar value from valid result', () => {
    const result = [{ metric: {}, value: [1234567890, '42.5'] as [number, string] }];
    expect(scalarValue(result)).toBe(42.5);
  });

  it('returns zero when value is "0"', () => {
    const result = [{ metric: {}, value: [1234567890, '0'] as [number, string] }];
    expect(scalarValue(result)).toBe(0);
  });

  it('handles negative values', () => {
    const result = [{ metric: {}, value: [1234567890, '-123.45'] as [number, string] }];
    expect(scalarValue(result)).toBe(-123.45);
  });

  it('ignores subsequent results and uses only first', () => {
    const results = [
      { metric: {}, value: [1234567890, '100'] as [number, string] },
      { metric: {}, value: [1234567890, '200'] as [number, string] },
    ];
    expect(scalarValue(results)).toBe(100);
  });

  it('handles scientific notation', () => {
    const result = [{ metric: {}, value: [123, '1.5e10'] as [number, string] }];
    expect(scalarValue(result)).toBe(15000000000);
  });

  it('handles very small numbers', () => {
    const result = [{ metric: {}, value: [123, '0.000001'] as [number, string] }];
    expect(scalarValue(result)).toBe(0.000001);
  });

  it('returns null for NaN string', () => {
    const result = [{ metric: {}, value: [123, 'NaN'] as [number, string] }];
    expect(scalarValue(result)).toBeNull();
  });

  it('handles Infinity string', () => {
    const result = [{ metric: {}, value: [123, 'Infinity'] as [number, string] }];
    // parseFloat('Infinity') returns Infinity, which is a valid number, not NaN
    expect(scalarValue(result)).toBe(Infinity);
  });
});

describe('groupByLabel', () => {
  it('returns empty object for null input', () => {
    expect(groupByLabel(null, 'status')).toEqual({});
  });

  it('returns empty object for empty array', () => {
    expect(groupByLabel([], 'status')).toEqual({});
  });

  it('groups results by label', () => {
    const results = [
      { metric: { status: '200' }, value: [123, '10'] as [number, string] },
      { metric: { status: '404' }, value: [123, '5'] as [number, string] },
      { metric: { status: '200' }, value: [123, '15'] as [number, string] },
    ];
    expect(groupByLabel(results, 'status')).toEqual({
      '200': 25,
      '404': 5,
    });
  });

  it('uses "unknown" for missing label', () => {
    const results = [
      { metric: {}, value: [123, '7'] as [number, string] },
      { metric: { status: '500' }, value: [123, '3'] as [number, string] },
    ];
    expect(groupByLabel(results, 'status')).toEqual({
      unknown: 7,
      '500': 3,
    });
  });

  it('handles missing value field', () => {
    const results = [
      { metric: { path: '/api' }, value: undefined },
      { metric: { path: '/api' }, value: [123, '10'] as [number, string] },
    ];
    expect(groupByLabel(results, 'path')).toEqual({
      '/api': 10,
    });
  });

  it('sums values for same label', () => {
    const results = [
      { metric: { method: 'GET' }, value: [123, '100'] as [number, string] },
      { metric: { method: 'GET' }, value: [123, '50'] as [number, string] },
      { metric: { method: 'POST' }, value: [123, '30'] as [number, string] },
    ];
    expect(groupByLabel(results, 'method')).toEqual({
      GET: 150,
      POST: 30,
    });
  });

  it('handles string labels with spaces', () => {
    const results = [
      { metric: { endpoint: 'api gateway' }, value: [123, '100'] as [number, string] },
      { metric: { endpoint: 'api gateway' }, value: [123, '50'] as [number, string] },
    ];
    expect(groupByLabel(results, 'endpoint')).toEqual({
      'api gateway': 150,
    });
  });

  it('handles special characters in label values', () => {
    const results = [
      { metric: { path: '/api/v1/users' }, value: [123, '10'] as [number, string] },
      { metric: { path: '/api/v1/users' }, value: [123, '5'] as [number, string] },
      { metric: { path: '/api/v2/tenants' }, value: [123, '8'] as [number, string] },
    ];
    expect(groupByLabel(results, 'path')).toEqual({
      '/api/v1/users': 15,
      '/api/v2/tenants': 8,
    });
  });

  it('handles empty string label value', () => {
    const results = [
      { metric: { tag: '' }, value: [123, '10'] as [number, string] },
      { metric: { tag: 'prod' }, value: [123, '20'] as [number, string] },
    ];
    // Empty string is treated as "unknown" by the groupByLabel function
    expect(groupByLabel(results, 'tag')).toEqual({
      unknown: 10,
      prod: 20,
    });
  });

  it('handles numeric label values as strings', () => {
    const results = [
      { metric: { code: '200' }, value: [123, '100'] as [number, string] },
      { metric: { code: '404' }, value: [123, '5'] as [number, string] },
      { metric: { code: '500' }, value: [123, '2'] as [number, string] },
    ];
    expect(groupByLabel(results, 'code')).toEqual({
      '200': 100,
      '404': 5,
      '500': 2,
    });
  });

  it('sums zero values correctly', () => {
    const results = [
      { metric: { status: '200' }, value: [123, '0'] as [number, string] },
      { metric: { status: '200' }, value: [123, '0'] as [number, string] },
    ];
    expect(groupByLabel(results, 'status')).toEqual({
      '200': 0,
    });
  });

  it('handles negative values', () => {
    const results = [
      { metric: { delta: 'negative' }, value: [123, '-10'] as [number, string] },
      { metric: { delta: 'negative' }, value: [123, '-5'] as [number, string] },
      { metric: { delta: 'positive' }, value: [123, '20'] as [number, string] },
    ];
    expect(groupByLabel(results, 'delta')).toEqual({
      negative: -15,
      positive: 20,
    });
  });

  it('handles fractional values', () => {
    const results = [
      { metric: { bucket: 'small' }, value: [123, '0.5'] as [number, string] },
      { metric: { bucket: 'small' }, value: [123, '0.3'] as [number, string] },
      { metric: { bucket: 'large' }, value: [123, '1.2'] as [number, string] },
    ];
    expect(groupByLabel(results, 'bucket')).toEqual({
      small: 0.8,
      large: 1.2,
    });
  });
});
