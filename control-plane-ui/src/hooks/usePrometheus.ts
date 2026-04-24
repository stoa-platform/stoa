import { useState, useEffect, useCallback, useRef } from 'react';

import { httpClient } from '../services/http';

// CAB-2029: Route through authenticated API proxy instead of unauthenticated nginx pass-through
const PROMETHEUS_BASE = '/api/v1/metrics';
const PROMETHEUS_TIMEOUT_MS = 10_000;

interface PrometheusResult {
  metric: Record<string, string>;
  value?: [number, string]; // instant query
  values?: [number, string][]; // range query
}

interface PrometheusResponse {
  status: string;
  data: {
    resultType: string;
    result: PrometheusResult[];
  };
}

export interface TimeSeriesPoint {
  timestamp: number;
  value: number;
}

/**
 * Execute a Prometheus instant query.
 * Returns the first scalar value or null if unavailable.
 */
export function usePrometheusQuery(query: string, refreshInterval = 15_000) {
  const [data, setData] = useState<PrometheusResult[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const fetchQuery = useCallback(async () => {
    if (!query) return;
    try {
      const { data: json } = await httpClient.get<PrometheusResponse>(`${PROMETHEUS_BASE}/query`, {
        params: { query },
        timeout: PROMETHEUS_TIMEOUT_MS,
      });
      if (mountedRef.current) {
        setData(json.data.result);
        setError(null);
      }
    } catch (err: unknown) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Prometheus unavailable');
        setData(null);
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    mountedRef.current = true;
    if (query) fetchQuery();
    if (refreshInterval > 0) {
      const interval = setInterval(fetchQuery, refreshInterval);
      return () => {
        mountedRef.current = false;
        clearInterval(interval);
      };
    }
    return () => {
      mountedRef.current = false;
    };
  }, [fetchQuery, refreshInterval, query]);

  return { data, loading, error, refetch: fetchQuery };
}

/**
 * Execute a Prometheus range query for time-series data (sparklines).
 */
export function usePrometheusRange(
  query: string,
  durationSeconds: number,
  step: string,
  refreshInterval = 15_000
) {
  const [data, setData] = useState<TimeSeriesPoint[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const fetchRange = useCallback(async () => {
    if (!query) return;
    try {
      const end = Math.floor(Date.now() / 1000);
      const start = end - durationSeconds;
      const { data: json } = await httpClient.get<PrometheusResponse>(
        `${PROMETHEUS_BASE}/query_range`,
        {
          params: { query, start, end, step },
          timeout: PROMETHEUS_TIMEOUT_MS,
        }
      );
      if (mountedRef.current) {
        const points: TimeSeriesPoint[] =
          json.data.result[0]?.values?.map(([ts, val]) => ({
            timestamp: ts,
            value: parseFloat(val) || 0,
          })) ?? [];
        setData(points);
        setError(null);
      }
    } catch (err: unknown) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Prometheus unavailable');
        setData(null);
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [query, durationSeconds, step]);

  useEffect(() => {
    mountedRef.current = true;
    if (query) fetchRange();
    if (refreshInterval > 0) {
      const interval = setInterval(fetchRange, refreshInterval);
      return () => {
        mountedRef.current = false;
        clearInterval(interval);
      };
    }
    return () => {
      mountedRef.current = false;
    };
  }, [fetchRange, refreshInterval, query]);

  return { data, loading, error, refetch: fetchRange };
}

/** Extract scalar value from instant query result */
export function scalarValue(results: PrometheusResult[] | null): number | null {
  if (!results || results.length === 0) return null;
  const val = results[0].value?.[1];
  if (val === undefined) return null;
  const n = parseFloat(val);
  return isNaN(n) ? null : n;
}

/** Extract results grouped by a label */
export function groupByLabel(
  results: PrometheusResult[] | null,
  label: string
): Record<string, number> {
  if (!results) return {};
  const groups: Record<string, number> = {};
  for (const r of results) {
    const key = r.metric[label] || 'unknown';
    groups[key] = (groups[key] || 0) + parseFloat(r.value?.[1] || '0');
  }
  return groups;
}
