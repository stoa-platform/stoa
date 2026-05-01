import { describe, expect, it } from 'vitest';
import {
  resolveInitialPortalEnvironment,
  type PortalEnvironmentConfig,
} from './EnvironmentContext';

const environments: PortalEnvironmentConfig[] = [
  {
    name: 'prod',
    label: 'Production',
    mode: 'read-only',
    color: 'red',
    is_current: true,
    endpoints: {
      api_url: 'https://api.gostoa.dev',
      keycloak_url: 'https://auth.gostoa.dev',
      keycloak_realm: 'stoa',
      mcp_url: 'https://mcp.gostoa.dev',
    },
  },
  {
    name: 'dev',
    label: 'Development',
    mode: 'full',
    color: 'green',
    endpoints: {
      api_url: 'https://dev-api.gostoa.dev',
      keycloak_url: 'https://dev-auth.gostoa.dev',
      keycloak_realm: 'stoa',
      mcp_url: 'https://dev-mcp.gostoa.dev',
    },
  },
];

describe('resolveInitialPortalEnvironment', () => {
  it('uses the current environment when no stored choice exists', () => {
    const resolved = resolveInitialPortalEnvironment(
      environments,
      null,
      'dev',
      'https://auth.gostoa.dev'
    );

    expect(resolved?.name).toBe('prod');
  });

  it('ignores a stored environment tied to a different Keycloak', () => {
    const resolved = resolveInitialPortalEnvironment(
      environments,
      'dev',
      'dev',
      'https://auth.gostoa.dev'
    );

    expect(resolved?.name).toBe('prod');
  });

  it('keeps a stored environment when it uses the current Keycloak', () => {
    const resolved = resolveInitialPortalEnvironment(
      environments,
      'prod',
      'dev',
      'https://auth.gostoa.dev'
    );

    expect(resolved?.name).toBe('prod');
  });
});
