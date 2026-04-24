import { createHttpInstance } from './client';
import { installRequestInterceptor } from './interceptors';
import { installRefreshInterceptor } from './refresh';

const instance = createHttpInstance();
installRequestInterceptor(instance);
installRefreshInterceptor(instance);

export const httpClient = instance;

export {
  setAuthToken,
  getAuthToken,
  clearAuthToken,
  setTokenRefresher,
  type TokenRefresher,
} from './auth';

export { refreshAuthTokenWithTimeout } from './refresh';

export { path } from './path';

export {
  createEventSource,
  openEventStream,
  type SseConnection,
  type SseEvent,
  type SseHandlers,
} from './sse';
