import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  useEffect,
  ReactNode,
} from 'react';
import { useAuth as useOidcAuth } from 'react-oidc-context';
import { useQueryClient } from '@tanstack/react-query';
import { config } from '../config';
import { setApiBaseUrl } from '../services/api';

const ACTIVE_ENV_KEY = 'stoa-portal-active-environment';

export type PortalEnvironment = 'dev' | 'staging' | 'prod';
export type PortalEnvironmentMode = 'full' | 'read-only' | 'promote-only';

export interface PortalEnvironmentEndpoints {
  api_url: string;
  keycloak_url: string;
  keycloak_realm: string;
  mcp_url: string;
}

export interface PortalEnvironmentConfig {
  name: PortalEnvironment;
  label: string;
  mode: PortalEnvironmentMode;
  color: string;
  endpoints?: PortalEnvironmentEndpoints | null;
  is_current?: boolean;
}

const FALLBACK_ENVIRONMENTS: PortalEnvironmentConfig[] = [
  { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
  { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
  { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' },
];

function toEnvironmentKey(name: string): PortalEnvironment {
  if (name === 'production' || name === 'prod') return 'prod';
  if (name === 'staging') return 'staging';
  return 'dev';
}

function isValidEnvironment(value: string): value is PortalEnvironment {
  return value === 'dev' || value === 'staging' || value === 'prod';
}

function getStoredEnvironment(): PortalEnvironment | null {
  const stored = localStorage.getItem(ACTIVE_ENV_KEY);
  return stored && isValidEnvironment(stored) ? stored : null;
}

function isSameKeycloak(env: PortalEnvironmentConfig, keycloakUrl: string): boolean {
  return !env.endpoints?.keycloak_url || env.endpoints.keycloak_url === keycloakUrl;
}

export function resolveInitialPortalEnvironment(
  environments: PortalEnvironmentConfig[],
  storedEnvironment: PortalEnvironment | null,
  configuredEnvironment: PortalEnvironment,
  keycloakUrl: string
): PortalEnvironmentConfig | undefined {
  const stored = storedEnvironment
    ? environments.find((env) => env.name === storedEnvironment && isSameKeycloak(env, keycloakUrl))
    : undefined;

  return (
    stored ??
    environments.find((env) => env.is_current) ??
    environments.find((env) => env.name === configuredEnvironment) ??
    environments[0]
  );
}

interface PortalEnvironmentContextType {
  activeEnvironment: PortalEnvironment;
  activeConfig: PortalEnvironmentConfig;
  environments: PortalEnvironmentConfig[];
  endpoints: PortalEnvironmentEndpoints | null;
  switchEnvironment: (env: PortalEnvironment) => void;
  loading: boolean;
  error: string | null;
}

const PortalEnvironmentContext = createContext<PortalEnvironmentContextType | undefined>(undefined);

export function PortalEnvironmentProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const oidcAuth = useOidcAuth();

  const [environments, setEnvironments] =
    useState<PortalEnvironmentConfig[]>(FALLBACK_ENVIRONMENTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeEnvironment, setActiveEnvironment] = useState<PortalEnvironment>(() => {
    return getStoredEnvironment() ?? toEnvironmentKey(config.app.environment);
  });

  useEffect(() => {
    const token = oidcAuth.user?.access_token;
    if (!token) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function fetchEnvironments() {
      try {
        const response = await fetch(`${config.api.baseUrl}/v1/environments`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (cancelled) return;

        const mapped: PortalEnvironmentConfig[] = data.environments.map(
          (env: {
            name: string;
            label: string;
            mode: string;
            color: string;
            endpoints: PortalEnvironmentEndpoints | null;
            is_current: boolean;
          }) => ({
            name: toEnvironmentKey(env.name),
            label: env.label,
            mode: env.mode as PortalEnvironmentConfig['mode'],
            color: env.color,
            endpoints: env.endpoints ?? null,
            is_current: env.is_current,
          })
        );

        setEnvironments(mapped);
        setError(null);

        const initialEnv = resolveInitialPortalEnvironment(
          mapped,
          getStoredEnvironment(),
          toEnvironmentKey(config.app.environment),
          config.keycloak.url
        );
        if (initialEnv) {
          setActiveEnvironment(initialEnv.name);
        }
        if (initialEnv?.endpoints?.api_url) {
          setApiBaseUrl(initialEnv.endpoints.api_url);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch environments');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchEnvironments();
    return () => {
      cancelled = true;
    };
  }, [oidcAuth.user?.access_token]);

  const activeConfig = useMemo(
    () => environments.find((e) => e.name === activeEnvironment) ?? environments[0],
    [activeEnvironment, environments]
  );

  const endpoints = useMemo(() => activeConfig?.endpoints ?? null, [activeConfig]);

  const switchEnvironment = useCallback(
    (env: PortalEnvironment) => {
      const newConfig = environments.find((e) => e.name === env);

      // Update API base URL for the new environment
      if (newConfig?.endpoints?.api_url) {
        setApiBaseUrl(newConfig.endpoints.api_url);
      } else {
        setApiBaseUrl(config.api.baseUrl);
      }

      // Cross-env auth: if Keycloak URL differs, force re-authentication
      const currentKcUrl = activeConfig?.endpoints?.keycloak_url;
      const newKcUrl = newConfig?.endpoints?.keycloak_url;
      if (currentKcUrl && newKcUrl && currentKcUrl !== newKcUrl) {
        // Different Keycloak instance — token is invalid for new env
        setActiveEnvironment(env);
        localStorage.setItem(ACTIVE_ENV_KEY, env);
        queryClient.invalidateQueries();
        void oidcAuth.signinRedirect();
        return;
      }

      setActiveEnvironment(env);
      localStorage.setItem(ACTIVE_ENV_KEY, env);
      queryClient.invalidateQueries();
    },
    [queryClient, environments, activeConfig, oidcAuth]
  );

  const value: PortalEnvironmentContextType = useMemo(
    () => ({
      activeEnvironment,
      activeConfig,
      environments,
      endpoints,
      switchEnvironment,
      loading,
      error,
    }),
    [activeEnvironment, activeConfig, environments, endpoints, switchEnvironment, loading, error]
  );

  return (
    <PortalEnvironmentContext.Provider value={value}>{children}</PortalEnvironmentContext.Provider>
  );
}

export function usePortalEnvironment() {
  const context = useContext(PortalEnvironmentContext);
  if (context === undefined) {
    throw new Error('usePortalEnvironment must be used within a PortalEnvironmentProvider');
  }
  return context;
}
