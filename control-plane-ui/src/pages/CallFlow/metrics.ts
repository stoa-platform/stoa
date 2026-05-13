import type { TimeRange } from '@stoa/shared/components/TimeRangeSelector';

export const MODE_FILTER = 'job=~"stoa-gateway|stoa-link|stoa-connect"';
export const ROUTE_LABEL = 'http_route';
export const UNLABELLED_ROUTE = '(unlabelled)';

export const ROUTE_LABELS_UNAVAILABLE_MESSAGE =
  'Route labels unavailable. Metrics currently do not expose a usable `http_route` label for route-level panels. Check Prometheus scrape config and gateway instrumentation.';

export const HEATMAP_EMPTY_MESSAGE = 'No route traffic in the last 24 hours.';

export const METRICS_TRACES_SPLIT_MESSAGE =
  'Request metrics are available, but no traces were found for this time range. Metrics source: Prometheus. Trace source: Tempo/OpenSearch pipeline.';

interface LiveCallsQueries {
  totalRequests: string;
  totalErrors: string;
  p50Latency: string;
  p99Latency: string;
  activeModes: string;
  edgeMcpTrend: string;
  sidecarTrend: string;
  connectTrend: string;
  latencyBuckets: string;
  statusMix: string;
  errorsByStatus: string;
  clientErrorsByStatus: string;
  topRoutesP95: string;
  topRoutesCalls: string;
  trafficHeatmap: string;
  requestsTrend: string;
}

const ROUTE_LABEL_FILTER = `${ROUTE_LABEL}!="", ${ROUTE_LABEL}!="unknown", ${ROUTE_LABEL}!="${UNLABELLED_ROUTE}"`;

export function buildLiveCallsQueries(timeRange: TimeRange): LiveCallsQueries {
  return {
    totalRequests: `sum(increase(stoa_http_requests_total{${MODE_FILTER}}[${timeRange}]))`,
    totalErrors: `sum(increase(stoa_http_requests_total{${MODE_FILTER}, status=~"5.."}[${timeRange}]))`,
    p50Latency: `histogram_quantile(0.50, sum(rate(stoa_http_request_duration_seconds_bucket{${MODE_FILTER}}[5m])) by (le))`,
    p99Latency: `histogram_quantile(0.99, sum(rate(stoa_http_request_duration_seconds_bucket{${MODE_FILTER}}[5m])) by (le))`,
    activeModes: `count(count by (job) (stoa_http_requests_total{${MODE_FILTER}}))`,
    edgeMcpTrend: `sum(rate(stoa_http_requests_total{${MODE_FILTER}, job="stoa-gateway"}[5m]))`,
    sidecarTrend: `sum(rate(stoa_http_requests_total{${MODE_FILTER}, job="stoa-link"}[5m]))`,
    connectTrend: `sum(rate(stoa_http_requests_total{${MODE_FILTER}, job="stoa-connect"}[5m]))`,
    latencyBuckets: `sum(increase(stoa_http_request_duration_seconds_bucket{${MODE_FILTER}}[${timeRange}])) by (le)`,
    statusMix: `sum by (status) (increase(stoa_http_requests_total{${MODE_FILTER}, status=~"2..|3..|4..|5.."}[${timeRange}]))`,
    errorsByStatus: `sum by (status) (increase(stoa_http_requests_total{${MODE_FILTER}, status=~"5.."}[${timeRange}]))`,
    clientErrorsByStatus: `sum by (status) (increase(stoa_http_requests_total{${MODE_FILTER}, status=~"4.."}[${timeRange}]))`,
    topRoutesP95: `topk(8, histogram_quantile(0.95, sum by (le, ${ROUTE_LABEL}) (rate(stoa_http_request_duration_seconds_bucket{${MODE_FILTER}, ${ROUTE_LABEL_FILTER}}[5m]))))`,
    topRoutesCalls: `sum by (${ROUTE_LABEL}) (increase(stoa_http_requests_total{${MODE_FILTER}, ${ROUTE_LABEL_FILTER}}[${timeRange}]))`,
    trafficHeatmap: `sum by (${ROUTE_LABEL}) (increase(stoa_http_requests_total{${MODE_FILTER}, ${ROUTE_LABEL_FILTER}}[1h]))`,
    requestsTrend: `sum(rate(stoa_http_requests_total{${MODE_FILTER}}[5m]))`,
  };
}

export function isRenderableRouteLabel(route: string): boolean {
  const normalized = route.trim().toLowerCase();
  return normalized !== '' && normalized !== 'unknown' && normalized !== UNLABELLED_ROUTE;
}

export function filterRenderableRoutes<T extends { route: string }>(routes: T[]): T[] {
  return routes.filter((route) => isRenderableRouteLabel(route.route));
}
