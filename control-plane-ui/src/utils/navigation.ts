/**
 * Navigation helpers for embedded service views (CAB-1108).
 * Converts external links into internal iframe routes with deep-link support.
 */

/** Build a path to the Observability iframe, optionally with a target URL. */
export function observabilityPath(targetUrl?: string): string {
  if (!targetUrl) return '/observability';
  return `/observability?url=${encodeURIComponent(targetUrl)}`;
}

/** Build a path to the Logs iframe, optionally with a target URL. */
export function logsPath(targetUrl?: string): string {
  if (!targetUrl) return '/logs';
  return `/logs?url=${encodeURIComponent(targetUrl)}`;
}

/** Allowed hostnames for embedded iframe URLs. */
const ALLOWED_HOSTS = ['grafana.gostoa.dev', 'prometheus.gostoa.dev', 'localhost'];

/** Validate that a URL is safe to embed in an iframe (no open redirect). */
export function isAllowedEmbedUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return ALLOWED_HOSTS.some(
      (host) => parsed.hostname === host || parsed.hostname.endsWith(`.${host}`)
    );
  } catch {
    // Relative URL or invalid — allow relative paths
    return url.startsWith('/');
  }
}
