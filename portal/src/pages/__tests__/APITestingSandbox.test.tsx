/**
 * APITestingSandbox Tests - CAB-1133
 *
 * Tests for the API testing sandbox page.
 * Route guard: scope="stoa:tools:execute" — viewer denied, others allowed.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import {
  renderWithProviders,
  createAuthMock,
  createPortalEnvironmentMock,
  mockAPI,
  type PersonaRole,
} from '../../test/helpers';
import { Routes, Route } from 'react-router-dom';
import { config as sandboxConfig } from '../../config';

// Mock useAPI hook
const mockUseAPI = vi.fn();
let mockEnvironment = createPortalEnvironmentMock();
vi.mock('../../hooks/useAPIs', () => ({
  useAPI: (id: string) => mockUseAPI(id),
}));

vi.mock('../../contexts/EnvironmentContext', () => ({
  usePortalEnvironment: () => mockEnvironment,
}));

// Mock config
vi.mock('../../config', () => ({
  config: {
    portalMode: 'development',
    baseDomain: 'gostoa.dev',
    testing: {
      gatewayBaseUrl: '',
      availableEnvironments: ['dev'],
      requireSandboxConfirmation: false,
    },
    api: { baseUrl: 'https://api.gostoa.dev' },
    mcp: { baseUrl: 'https://mcp.gostoa.dev' },
    keycloak: {
      url: 'https://auth.gostoa.dev',
      realm: 'stoa',
      clientId: 'stoa-portal',
      authority: 'https://auth.gostoa.dev/realms/stoa',
    },
  },
}));

// Mock testing components
vi.mock('../../components/testing', () => ({
  EnvironmentSelector: ({
    onSelect,
    environments,
  }: {
    onSelect: (env: { id: string }) => void;
    environments: unknown[];
  }) => (
    <div data-testid="environment-selector" data-environments={JSON.stringify(environments)}>
      <button onClick={() => onSelect({ id: 'dev' })}>Select Env</button>
    </div>
  ),
  RequestBuilder: ({
    baseUrl,
    initialPath,
    disabled,
  }: {
    baseUrl: string;
    initialPath: string;
    disabled: boolean;
  }) => (
    <div
      data-testid="request-builder"
      data-base-url={baseUrl}
      data-path={initialPath}
      data-disabled={disabled}
    >
      Request Builder
    </div>
  ),
  ResponseViewer: () => <div data-testid="response-viewer">Response Viewer</div>,
  SandboxConfirmationModal: () => null,
}));

describe('APITestingSandbox', () => {
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      let APITestingSandbox: React.ComponentType;

      beforeEach(async () => {
        vi.clearAllMocks();
        mockEnvironment = createPortalEnvironmentMock();

        const pageModule = await import('../apis/APITestingSandbox');
        APITestingSandbox = pageModule.APITestingSandbox;
      });

      const renderWithRoute = (apiId: string = 'api-1') => {
        return renderWithProviders(
          <Routes>
            <Route path="/apis/:id/test" element={<APITestingSandbox />} />
          </Routes>,
          { route: `/apis/${apiId}/test` }
        );
      };

      it('shows loading state', () => {
        mockUseAPI.mockReturnValue({ data: undefined, isLoading: true, isError: false });

        renderWithRoute();

        expect(screen.getByText('Loading API details...')).toBeInTheDocument();
      });

      it('shows error state when API not found', async () => {
        mockUseAPI.mockReturnValue({
          data: undefined,
          isLoading: false,
          isError: true,
          error: new Error('Not found'),
        });

        renderWithRoute();

        await waitFor(() => {
          expect(screen.getByText('Failed to load API')).toBeInTheDocument();
        });
      });

      it('renders sandbox heading with API name', async () => {
        mockUseAPI.mockReturnValue({
          data: mockAPI({ name: 'Payment API' }),
          isLoading: false,
          isError: false,
        });

        renderWithRoute();

        await waitFor(() => {
          expect(screen.getByText('API Testing Sandbox')).toBeInTheDocument();
        });
      });

      it('renders environment selector and request builder', async () => {
        mockUseAPI.mockReturnValue({
          data: mockAPI(),
          isLoading: false,
          isError: false,
        });

        renderWithRoute();

        await waitFor(() => {
          expect(screen.getByTestId('environment-selector')).toBeInTheDocument();
          expect(screen.getByTestId('request-builder')).toBeInTheDocument();
        });
      });

      it('should have correct stoa:tools:execute scope for role', () => {
        const auth = createAuthMock(role);
        const expected = role !== 'viewer';
        expect(auth.hasScope('stoa:tools:execute')).toBe(expected);
      });
    }
  );
});

describe('private gateway environment resolution', () => {
  const originalMode = sandboxConfig.portalMode;

  beforeEach(() => {
    sandboxConfig.testing.gatewayBaseUrl = '/api';
    mockEnvironment = createPortalEnvironmentMock();
    mockUseAPI.mockReturnValue({
      data: mockAPI({ id: 'orders', endpoints: [{ path: '/customers' }] }),
      isLoading: false,
      isError: false,
    });
  });

  afterEach(() => {
    sandboxConfig.testing.gatewayBaseUrl = '';
    sandboxConfig.portalMode = originalMode;
    mockEnvironment = createPortalEnvironmentMock();
  });

  const renderSandbox = async () => {
    const { APITestingSandbox } = await import('../apis/APITestingSandbox');
    renderWithProviders(
      <Routes>
        <Route path="/apis/:id/test" element={<APITestingSandbox />} />
      </Routes>,
      { route: '/apis/orders/test' }
    );
  };

  const visibleEnvironments = () =>
    JSON.parse(
      screen.getByTestId('environment-selector').getAttribute('data-environments') || '[]'
    );

  it('keeps the historical URL without an override', async () => {
    sandboxConfig.testing.gatewayBaseUrl = '';
    sandboxConfig.portalMode = 'production';
    await renderSandbox();
    expect(visibleEnvironments()).toEqual([
      {
        id: 'prod',
        name: 'prod',
        displayName: 'Production',
        baseUrl: 'https://apis.gostoa.dev',
        isProduction: true,
      },
    ]);
  });

  it('uses only the current environment supplied by the control plane', async () => {
    mockEnvironment = createPortalEnvironmentMock({
      environments: [
        {
          name: 'staging',
          label: 'Current from CP',
          mode: 'full',
          color: 'amber',
          is_current: true,
        },
        {
          name: 'prod',
          label: 'Other from CP',
          mode: 'read-only',
          color: 'red',
          is_current: false,
        },
      ],
    });
    await renderSandbox();
    expect(visibleEnvironments()).toEqual([
      {
        id: 'staging',
        name: 'staging',
        displayName: 'Current from CP',
        baseUrl: '/api',
        isProduction: false,
      },
    ]);
  });

  it.each([
    { loading: true },
    { error: 'HTTP 403' },
    { environments: [] },
    {
      environments: [
        {
          name: 'dev' as const,
          label: 'Not current',
          mode: 'full' as const,
          color: 'green',
          is_current: false,
        },
      ],
    },
  ])(
    'disables requests without a public fallback when the CP target is unavailable: %o',
    async (state) => {
      mockEnvironment = createPortalEnvironmentMock(state);
      await renderSandbox();
      expect(visibleEnvironments()).toEqual([]);
      expect(screen.getByTestId('request-builder')).toHaveAttribute('data-disabled', 'true');
      expect(screen.getByTestId('request-builder')).toHaveAttribute('data-base-url', '');
    }
  );

  it('shows the actual private API prefix separately from the operation path', async () => {
    await renderSandbox();
    expect(screen.getByTestId('request-builder')).toHaveAttribute(
      'data-base-url',
      '/api/apis/orders'
    );
    expect(screen.getByTestId('request-builder')).toHaveAttribute('data-path', '/customers');
  });
});
