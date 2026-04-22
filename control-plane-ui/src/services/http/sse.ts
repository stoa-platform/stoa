import { config } from '../../config';

export function createEventSource(tenantId: string, eventTypes?: string[]): EventSource {
  const params = eventTypes ? `?event_types=${eventTypes.join(',')}` : '';
  const url = `${config.api.baseUrl}/v1/events/stream/${tenantId}${params}`;
  return new EventSource(url);
}
