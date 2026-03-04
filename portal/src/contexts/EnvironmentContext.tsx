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
  name: string;
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
    const stored = localStorage.getItem(ACTIVE_ENV_KEY);
    if (stored && isValidEnvironment(stored)) return stored;
    return 'dev';
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
      setActiveEnvironment(env);
      localStorage.setItem(ACTIVE_ENV_KEY, env);
      queryClient.invalidateQueries();
    },
    [queryClient]
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
