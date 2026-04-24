/**
 * Build an absolute URL path from raw path segments.
 *
 * Always returns a leading slash followed by each segment encoded via
 * encodeURIComponent. Pass segments WITHOUT slashes — each segment is
 * treated as a single opaque identifier. A segment containing '/' will
 * be encoded to '%2F' and will NOT create a hierarchical path.
 *
 * Use for interpolating runtime values (tenantId, apiId, slug, etc.) into
 * path templates. Query parameters should go through axios `params` option,
 * not through this helper.
 *
 * @example
 *   path('v1', 'tenants', tenantId)
 *   // -> '/v1/tenants/<encoded>'
 *
 *   path('v1', 'tenants', tenantId, 'apis', apiId)
 *   // -> '/v1/tenants/<encoded>/apis/<encoded>'
 */
export function path(...segments: string[]): string {
  return '/' + segments.map(encodeURIComponent).join('/');
}
