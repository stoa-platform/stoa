// =============================================================================
// Grafana Faro SDK - Real User Monitoring (RUM)
// =============================================================================
// Phase 6: Frontend observability for STOA Developer Portal
//
// Captures:
//   - Web Vitals (LCP, FID, CLS, TTFB, FCP, INP)
//   - JavaScript errors + unhandled promise rejections
//   - Console errors
//   - Frontend traces (navigation, user interactions)
//   - Session metadata (user_id, tenant_id)
//
// Data flow:
//   Faro SDK -> Alloy Faro receiver (:12347) -> Loki (logs) + Tempo (traces)
// =============================================================================

import { getWebInstrumentations, initializeFaro } from '@grafana/faro-web-sdk';
import { TracingInstrumentation } from '@grafana/faro-web-tracing';

let faroInstance: ReturnType<typeof initializeFaro> | null = null;

interface FaroConfig {
  collectorUrl?: string;
  appName?: string;
  appVersion?: string;
  environment?: string;
}

/**
 * Initialize Grafana Faro for frontend observability.
 * Call this once at application boot (before React renders).
 */
export function initFaro(config: FaroConfig = {}): void {
  if (typeof window === 'undefined' || import.meta.env.MODE === 'test') {
    return;
  }

  const collectorUrl =
    config.collectorUrl ||
    import.meta.env.VITE_FARO_COLLECTOR_URL ||
    '/faro/collect';

  if (faroInstance) {
    return;
  }

  try {
    faroInstance = initializeFaro({
      url: collectorUrl,
      app: {
        name: config.appName || 'stoa-portal',
        version: config.appVersion || import.meta.env.VITE_APP_VERSION || '0.0.0',
        environment: config.environment || import.meta.env.VITE_ENVIRONMENT || 'production',
      },

      instrumentations: [
        ...getWebInstrumentations({
          captureConsole: true,
          captureConsoleDisabledLevels: ['debug', 'trace'],
        }),

        new TracingInstrumentation({
          instrumentationOptions: {
            propagateTraceHeaderCorsUrls: [
              new RegExp(`https?://api\\..*`),
              new RegExp(`https?://mcp\\..*`),
            ],
          },
        }),
      ],

      sessionTracking: {
        enabled: true,
        persistent: true,
        samplingRate: 1.0,
      },

      batching: {
        enabled: true,
        sendTimeout: 250,
        itemLimit: 50,
      },

      beforeSend: (item) => {
        if (item.type === 'error') {
          const message = (item as { payload?: { message?: string } }).payload?.message || '';
          if (message.includes('ResizeObserver loop')) {
            return null;
          }
        }
        return item;
      },
    });
  } catch (err) {
    console.warn('[Faro] Failed to initialize:', err);
  }
}

/**
 * Set user context after authentication.
 */
export function setFaroUser(user: {
  id: string;
  email?: string;
  name?: string;
  tenantId?: string;
}): void {
  if (!faroInstance) return;

  try {
    faroInstance.api.setUser({
      id: user.id,
      email: user.email,
      username: user.name,
      attributes: {
        ...(user.tenantId && { tenant_id: user.tenantId }),
      },
    });
  } catch {
    // Silently fail
  }
}

/**
 * Push a custom event to Faro.
 */
export function pushFaroEvent(name: string, attributes?: Record<string, string>): void {
  if (!faroInstance) return;

  try {
    faroInstance.api.pushEvent(name, attributes);
  } catch {
    // Silently fail
  }
}

export function getFaroInstance() {
  return faroInstance;
}
