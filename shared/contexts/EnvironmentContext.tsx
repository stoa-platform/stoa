import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from 'react';

// ============================================================================
// Types
// ============================================================================

export type EnvironmentMode = 'full' | 'read-only' | 'promote-only';

export interface EnvironmentEndpoints {
  api_url: string;
  keycloak_url: string;
  keycloak_realm: string;
  mcp_url: string;
}

export interface EnvironmentConfig {
  name: string;
  label: string;
  mode: EnvironmentMode;
  color: string;
  endpoints: EnvironmentEndpoints | null;
  is_current: boolean;
}

export interface EnvironmentListResponse {
  environments: EnvironmentConfig[];
  current: string;
}

interface EnvironmentContextValue {
  /** All available environments */
  environments: EnvironmentConfig[];
  /** Currently selected environment */
  current: EnvironmentConfig | null;
  /** Name of the current environment */
  currentName: string;
  /** Switch to a different environment by name */
  switchEnvironment: (name: string) => void;
  /** Whether environments are loading */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
}

// ============================================================================
// Context
// ============================================================================

const EnvironmentContext = createContext<EnvironmentContextValue | null>(null);

const STORAGE_KEY = 'stoa-environment';

// ============================================================================
// Provider
// ============================================================================

interface EnvironmentProviderProps {
  children: React.ReactNode;
  /** API base URL to fetch environments from (e.g., https://api.gostoa.dev) */
  apiBaseUrl: string;
  /** Auth token getter — called before each API request */
  getAccessToken: () => Promise<string | null>;
}

export function EnvironmentProvider({
  children,
  apiBaseUrl,
  getAccessToken,
}: EnvironmentProviderProps) {
  const [environments, setEnvironments] = useState<EnvironmentConfig[]>([]);
  const [serverDefault, setServerDefault] = useState<string>('');
  const [selectedName, setSelectedName] = useState<string>(() => {
    if (typeof window === 'undefined') return '';
    return localStorage.getItem(STORAGE_KEY) || '';
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch environments from the API
  useEffect(() => {
    let cancelled = false;

    async function fetchEnvironments() {
      try {
        const token = await getAccessToken();
        if (!token) {
          // Not authenticated yet — will retry after auth
          setLoading(false);
          return;
        }

        const response = await fetch(`${apiBaseUrl}/v1/environments`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch environments: ${response.status}`);
        }

        const data: EnvironmentListResponse = await response.json();
        if (!cancelled) {
          setEnvironments(data.environments);
          setServerDefault(data.current);
          setError(null);

          // If no saved selection, use server default
          if (!selectedName) {
            setSelectedName(data.current);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load environments');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchEnvironments();
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, getAccessToken, selectedName]);

  // Resolve current environment
  const current = useMemo(() => {
    const name = selectedName || serverDefault;
    return environments.find((e) => e.name === name) || environments[0] || null;
  }, [environments, selectedName, serverDefault]);

  const currentName = current?.name || selectedName || serverDefault;

  // Switch environment with persistence
  const switchEnvironment = useCallback(
    (name: string) => {
      const env = environments.find((e) => e.name === name);
      if (!env) return;
      setSelectedName(name);
      localStorage.setItem(STORAGE_KEY, name);
    },
    [environments]
  );

  const value = useMemo(
    () => ({
      environments,
      current,
      currentName,
      switchEnvironment,
      loading,
      error,
    }),
    [environments, current, currentName, switchEnvironment, loading, error]
  );

  return <EnvironmentContext.Provider value={value}>{children}</EnvironmentContext.Provider>;
}

// ============================================================================
// Hook
// ============================================================================

export function useEnvironment() {
  const context = useContext(EnvironmentContext);
  if (!context) {
    throw new Error('useEnvironment must be used within an EnvironmentProvider');
  }
  return context;
}

export default EnvironmentProvider;
