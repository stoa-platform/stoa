import { Activity } from 'lucide-react';
import { useServiceHealth } from '../hooks/useServiceHealth';
import { ServiceUnavailable } from './ServiceUnavailable';
import { useAuth } from '../contexts/AuthContext';
import { config } from '../config';

interface GrafanaPanelProps {
  dashboardUid: string;
  panelId: number;
  title?: string;
  height?: number;
  from?: string;
  to?: string;
  theme?: 'light' | 'dark';
  variables?: Record<string, string>;
  className?: string;
}

/**
 * Embeds a single Grafana panel via `/d-solo/` iframe.
 *
 * Authentication: passes the Keycloak JWT as `auth_token` URL parameter.
 * Grafana validates the JWT via JWKS and issues a session cookie
 * (`enable_login_token = true`), so subsequent loads don't need the token.
 *
 * RBAC: Grafana maps Keycloak roles to Grafana roles via `role_attribute_path`.
 * The Console UI RBAC gating (e.g., Traffic & Security section) is UX-level only.
 */
export function GrafanaPanel({
  dashboardUid,
  panelId,
  title,
  height = 200,
  from = 'now-1h',
  to = 'now',
  theme = 'light',
  variables,
  className,
}: GrafanaPanelProps) {
  const baseUrl = config.services.grafana.url;
  const { status, retry } = useServiceHealth(baseUrl);
  const { accessToken } = useAuth();

  const params = new URLSearchParams({
    orgId: '1',
    panelId: String(panelId),
    from,
    to,
    theme,
  });

  if (variables) {
    for (const [key, value] of Object.entries(variables)) {
      params.set(`var-${key}`, value);
    }
  }

  // Pass Keycloak JWT for Grafana [auth.jwt] url_login validation
  if (accessToken) {
    params.set('auth_token', accessToken);
  }

  const iframeSrc = `${baseUrl}d-solo/${dashboardUid}/?${params.toString()}`;

  if (status === 'unavailable') {
    return (
      <div className={className}>
        <ServiceUnavailable
          serviceName="Grafana"
          description="Grafana is not reachable. Metrics panels are temporarily unavailable."
          icon={Activity}
          externalUrl={baseUrl}
          onRetry={retry}
        />
      </div>
    );
  }

  return (
    <div className={className}>
      {title && (
        <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{title}</h3>
      )}
      {status === 'checking' ? (
        <div
          className="flex items-center justify-center bg-neutral-50 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700"
          style={{ height }}
        >
          <div className="animate-pulse text-sm text-neutral-400">Loading panel...</div>
        </div>
      ) : (
        <iframe
          src={iframeSrc}
          width="100%"
          height={height}
          frameBorder="0"
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
          className="rounded-lg border border-neutral-200 dark:border-neutral-700"
          title={title || `Grafana panel ${panelId}`}
        />
      )}
    </div>
  );
}
