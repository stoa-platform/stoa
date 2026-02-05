// =============================================================================
// Grafana Faro SDK - Real User Monitoring (RUM)
// =============================================================================
// Phase 6: Frontend observability for STOA Console UI
//
// Captures:
//   - Web Vitals (LCP, FID, CLS, TTFB, FCP, INP)
//   - JavaScript errors + unhandled promise rejections
//   - Console errors
//   - Frontend traces (navigation, user interactions)
//   - Session metadata (user_id, tenant_id, role)
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
 *
 * Faro collector URL defaults to the Alloy Faro receiver endpoint.
 * In production, this is exposed via the alloy service on port 12347.
 */
export function initFaro(config: FaroConfig = {}): void {
  // Skip in test environments
  if (typeof window === 'undefined' || import.meta.env.MODE === 'test') {
    return;
  }

  const collectorUrl =
    config.collectorUrl ||
    import.meta.env.VITE_FARO_COLLECTOR_URL ||
    '/faro/collect';

  // Don't double-initialize
  if (faroInstance) {
    return;
  }

  try {
    faroInstance = initializeFaro({
      url: collectorUrl,
      app: {
        name: config.appName || 'stoa-console',
        version: config.appVersion || import.meta.env.VITE_APP_VERSION || '0.0.0',
        environment: config.environment || import.meta.env.VITE_ENVIRONMENT || 'production',
      },

      instrumentations: [
        // Web Vitals + error capture + console instrumentation
        ...getWebInstrumentations({
          captureConsole: true,
          captureConsoleDisabledLevels: ['debug', 'trace'],
        }),

        // Distributed tracing (W3C TraceContext propagation)
        new TracingInstrumentation({
          instrumentationOptions: {
            propagateTraceHeaderCorsUrls: [
              // Propagate trace context to STOA backends
              new RegExp(`https?://api\\..*`),
              new RegExp(`https?://mcp\\..*`),
            ],
          },
        }),
      ],

      // Session tracking
      sessionTracking: {
        enabled: true,
        persistent: true,
        samplingRate: 1.0,
      },

      // Batching configuration (reduce network overhead)
      batching: {
        enabled: true,
        sendTimeout: 250,
        itemLimit: 50,
      },

      // Don't send events before user interaction (reduces noise)
      beforeSend: (item) => {
        // Filter out known noisy errors
        if (item.type === 'error') {
          const message = (item as { payload?: { message?: string } }).payload?.message || '';
          // Skip ResizeObserver loop errors (browser bug, harmless)
          if (message.includes('ResizeObserver loop')) {
            return null;
          }
        }
        return item;
      },
    });
  } catch (err) {
    // Faro init failure should never break the app
    console.warn('[Faro] Failed to initialize:', err);
  }
}

/**
 * Set user context after authentication.
 * Call this when the user logs in or when user data becomes available.
 */
export function setFaroUser(user: {
  id: string;
  email?: string;
  name?: string;
  tenantId?: string;
  role?: string;
}): void {
  if (!faroInstance) return;

  try {
    faroInstance.api.setUser({
      id: user.id,
      email: user.email,
      username: user.name,
      attributes: {
        ...(user.tenantId && { tenant_id: user.tenantId }),
        ...(user.role && { role: user.role }),
      },
    });
  } catch {
    // Silently fail - observability should never break the app
  }
}

/**
 * Push a custom event to Faro (for business metric tracking).
 */
export function pushFaroEvent(name: string, attributes?: Record<string, string>): void {
  if (!faroInstance) return;

  try {
    faroInstance.api.pushEvent(name, attributes);
  } catch {
    // Silently fail
  }
}

/**
 * Get the Faro instance for advanced usage.
 */
export function getFaroInstance() {
  return faroInstance;
}
