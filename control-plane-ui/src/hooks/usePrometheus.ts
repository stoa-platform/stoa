import { useState, useEffect, useCallback, useRef } from 'react';

const PROMETHEUS_BASE = '/prometheus/api/v1';

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
    try {
      const url = `${PROMETHEUS_BASE}/query?query=${encodeURIComponent(query)}`;
      const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error(`Prometheus returned ${response.status}`);
      const json: PrometheusResponse = await response.json();
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
    fetchQuery();
    const interval = setInterval(fetchQuery, refreshInterval);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [fetchQuery, refreshInterval]);

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
    try {
      const end = Math.floor(Date.now() / 1000);
      const start = end - durationSeconds;
      const url = `${PROMETHEUS_BASE}/query_range?query=${encodeURIComponent(query)}&start=${start}&end=${end}&step=${step}`;
      const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error(`Prometheus returned ${response.status}`);
      const json: PrometheusResponse = await response.json();
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
    fetchRange();
    const interval = setInterval(fetchRange, refreshInterval);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [fetchRange, refreshInterval]);

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
