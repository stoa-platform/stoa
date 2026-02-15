/**
 * APITestingSandbox Tests - CAB-1133
 *
 * Tests for the API testing sandbox page.
 * Route guard: scope="stoa:tools:execute" — viewer denied, others allowed.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock, mockAPI, type PersonaRole } from '../../test/helpers';
import { Routes, Route } from 'react-router-dom';

// Mock useAPI hook
const mockUseAPI = vi.fn();
vi.mock('../../hooks/useAPIs', () => ({
  useAPI: (id: string) => mockUseAPI(id),
}));

// Mock config
vi.mock('../../config', () => ({
  config: {
    portalMode: 'development',
    baseDomain: 'gostoa.dev',
    testing: {
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
  EnvironmentSelector: ({ onSelect }: { onSelect: (env: { id: string }) => void }) => (
    <div data-testid="environment-selector">
      <button onClick={() => onSelect({ id: 'dev' })}>Select Env</button>
    </div>
  ),
  RequestBuilder: () => <div data-testid="request-builder">Request Builder</div>,
  ResponseViewer: () => <div data-testid="response-viewer">Response Viewer</div>,
  SandboxConfirmationModal: () => null,
}));

describe('APITestingSandbox', () => {
  let APITestingSandbox: React.ComponentType;

  beforeEach(async () => {
    vi.clearAllMocks();

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

  describe('Persona-based Tests', () => {
    const allowedPersonas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops'];

    it.each(allowedPersonas)('%s has stoa:tools:execute scope for API testing', (persona) => {
      const auth = createAuthMock(persona);
      expect(auth.hasScope('stoa:tools:execute')).toBe(true);
    });

    it('viewer does not have stoa:tools:execute scope', () => {
      const auth = createAuthMock('viewer');
      expect(auth.hasScope('stoa:tools:execute')).toBe(false);
    });
  });
});
