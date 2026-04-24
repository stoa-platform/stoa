import { config } from '../../config';
import { path } from './path';

export function createEventSource(tenantId: string, eventTypes?: string[]): EventSource {
  const search = new URLSearchParams();
  if (eventTypes?.length) search.set('event_types', eventTypes.join(','));
  const qs = search.toString();
  const url = `${config.api.baseUrl}${path('v1', 'events', 'stream', tenantId)}${qs ? '?' + qs : ''}`;
  return new EventSource(url);
}
