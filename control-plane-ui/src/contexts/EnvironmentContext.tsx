import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  useEffect,
  ReactNode,
} from 'react';
import { useAuth } from 'react-oidc-context';
import { useQueryClient } from '@tanstack/react-query';
import { config } from '../config';
import type { Environment, EnvironmentConfig, EnvironmentEndpoints } from '../types';

const ACTIVE_ENV_KEY = 'stoa-active-environment';

const FALLBACK_ENVIRONMENTS: EnvironmentConfig[] = [
  { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
  { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
  { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' },
];

/** Map API environment names (e.g. "production") to local keys */
function toEnvironmentKey(name: string): Environment {
  if (name === 'production' || name === 'prod') return 'prod';
  if (name === 'staging') return 'staging';
  return 'dev';
}

function isValidEnvironment(value: string): value is Environment {
  return value === 'dev' || value === 'staging' || value === 'prod';
}

interface EnvironmentContextType {
  activeEnvironment: Environment;
  activeConfig: EnvironmentConfig;
  environments: EnvironmentConfig[];
  endpoints: EnvironmentEndpoints | null;
  switchEnvironment: (env: Environment) => void;
  loading: boolean;
  error: string | null;
}

const EnvironmentContext = createContext<EnvironmentContextType | undefined>(undefined);

export function EnvironmentProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const oidcAuth = useAuth();

  const [environments, setEnvironments] = useState<EnvironmentConfig[]>(FALLBACK_ENVIRONMENTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeEnvironment, setActiveEnvironment] = useState<Environment>(() => {
    const stored = localStorage.getItem(ACTIVE_ENV_KEY);
    if (stored && isValidEnvironment(stored)) return stored;
    return 'dev';
  });

  // Fetch environments from API
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

        const mapped: EnvironmentConfig[] = data.environments.map(
          (env: {
            name: string;
            label: string;
            mode: string;
            color: string;
            endpoints: EnvironmentEndpoints | null;
            is_current: boolean;
          }) => ({
            name: toEnvironmentKey(env.name),
            label: env.label,
            mode: env.mode as EnvironmentConfig['mode'],
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
    (env: Environment) => {
      setActiveEnvironment(env);
      localStorage.setItem(ACTIVE_ENV_KEY, env);
      queryClient.invalidateQueries();
    },
    [queryClient]
  );

  const value: EnvironmentContextType = useMemo(
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

  return <EnvironmentContext.Provider value={value}>{children}</EnvironmentContext.Provider>;
}

export function useEnvironment() {
  const context = useContext(EnvironmentContext);
  if (context === undefined) {
    throw new Error('useEnvironment must be used within an EnvironmentProvider');
  }
  return context;
}
