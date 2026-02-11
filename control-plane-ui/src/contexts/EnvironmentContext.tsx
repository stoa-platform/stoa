import { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Environment, EnvironmentConfig } from '../types';

const ACTIVE_ENV_KEY = 'stoa-active-environment';

const DEFAULT_ENVIRONMENTS: EnvironmentConfig[] = [
  { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
  { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
  { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' },
];

interface EnvironmentContextType {
  activeEnvironment: Environment;
  activeConfig: EnvironmentConfig;
  environments: EnvironmentConfig[];
  switchEnvironment: (env: Environment) => void;
}

const EnvironmentContext = createContext<EnvironmentContextType | undefined>(undefined);

export function EnvironmentProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const [activeEnvironment, setActiveEnvironment] = useState<Environment>(() => {
    const stored = localStorage.getItem(ACTIVE_ENV_KEY);
    if (stored === 'dev' || stored === 'staging' || stored === 'prod') {
      return stored;
    }
    return 'dev';
  });

  const activeConfig = useMemo(
    () => DEFAULT_ENVIRONMENTS.find((e) => e.name === activeEnvironment) ?? DEFAULT_ENVIRONMENTS[0],
    [activeEnvironment]
  );

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
      environments: DEFAULT_ENVIRONMENTS,
      switchEnvironment,
    }),
    [activeEnvironment, activeConfig, switchEnvironment]
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
