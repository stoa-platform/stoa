/**
 * Extract a list from a paginated or raw-array response.
 *
 * Some control-plane endpoints return a bare array (`[...]`), others a
 * paginated envelope (`{ items: [...], total, page, ... }`). Domain clients
 * used to paper over the difference with `return data.items ?? data`, which
 * silently returned the wrong shape (the envelope itself, cast as `T[]`)
 * whenever the backend changed to an unexpected response — the frontend
 * then crashed far downstream with an obscure `undefined.map is not a
 * function` or a false-typed object leaking into rendering.
 *
 * This helper fails fast with a labelled error so backend schema drift
 * surfaces at the boundary.
 */
export function extractList<T>(data: unknown, label: string): T[] {
  if (Array.isArray(data)) return data as T[];
  if (
    data !== null &&
    typeof data === 'object' &&
    'items' in data &&
    Array.isArray((data as { items: unknown }).items)
  ) {
    return (data as { items: T[] }).items;
  }
  throw new Error(`Unexpected ${label} response shape: expected array or { items: [...] }`);
}
