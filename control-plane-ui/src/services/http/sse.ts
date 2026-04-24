import { fetchEventSource } from '@microsoft/fetch-event-source';
import { config } from '../../config';
import { clearAuthToken, getAuthToken } from './auth';
import { path } from './path';
import { refreshAuthTokenWithTimeout } from './refresh';

export interface SseEvent {
  data: string;
  event?: string;
  id?: string;
}

export interface SseHandlers {
  onMessage: (event: SseEvent) => void;
  onOpen?: () => void;
  onError?: (error: unknown) => void;
}

export interface SseConnection {
  close(): void;
}

class RetriableError extends Error {}
class FatalError extends Error {}

/**
 * Custom fetch wrapper used by fetchEventSource. The lib's `headers` option
 * is a static Record<string,string> captured once at init, so a custom
 * `fetch` is the only reliable way to re-read the auth token on each
 * network call (including automatic retries after a disconnect).
 */
function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const token = getAuthToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  } else {
    headers.delete('Authorization');
  }
  return fetch(input, { ...init, headers });
}

export function openEventStream(
  tenantId: string,
  eventTypes: string[] | undefined,
  handlers: SseHandlers
): SseConnection {
  const controller = new AbortController();
  const search = new URLSearchParams();
  if (eventTypes?.length) search.set('event_types', eventTypes.join(','));
  const qs = search.toString();
  const url = `${config.api.baseUrl}${path('v1', 'events', 'stream', tenantId)}${
    qs ? '?' + qs : ''
  }`;

  void fetchEventSource(url, {
    signal: controller.signal,
    fetch: authFetch,
    openWhenHidden: false,
    onopen: async (response) => {
      if (response.ok) {
        handlers.onOpen?.();
        return;
      }
      if (response.status === 401) {
        try {
          await refreshAuthTokenWithTimeout();
          throw new RetriableError('SSE 401 — retrying with refreshed token');
        } catch (err) {
          if (err instanceof RetriableError) throw err;
          clearAuthToken();
          throw new FatalError(`SSE auth refresh failed: ${String(err)}`);
        }
      }
      if (response.status >= 400 && response.status < 500) {
        throw new FatalError(`SSE rejected: ${response.status}`);
      }
      throw new RetriableError(`SSE transient failure: ${response.status}`);
    },
    onmessage: (msg) => {
      handlers.onMessage({ data: msg.data, event: msg.event, id: msg.id });
    },
    onerror: (err) => {
      handlers.onError?.(err);
      if (err instanceof FatalError) {
        throw err;
      }
      // Return undefined to let the lib retry with its default backoff.
    },
  }).catch((err) => {
    handlers.onError?.(err);
  });

  return {
    close: () => controller.abort(),
  };
}

/**
 * @deprecated — kept for transitional compatibility with callers that still
 * expect a raw EventSource. New code must use openEventStream, which handles
 * authentication + retry correctly. Native EventSource cannot send custom
 * headers and therefore cannot authenticate against the backend SSE endpoint
 * (see ARB-4 in FIX-PLAN-UI2-P0.md).
 */
export function createEventSource(tenantId: string, eventTypes?: string[]): EventSource {
  const search = new URLSearchParams();
  if (eventTypes?.length) search.set('event_types', eventTypes.join(','));
  const qs = search.toString();
  const url = `${config.api.baseUrl}${path('v1', 'events', 'stream', tenantId)}${
    qs ? '?' + qs : ''
  }`;
  return new EventSource(url);
}
