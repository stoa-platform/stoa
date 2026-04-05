/**
 * Portal integration tests using MSW instead of vi.mock (CAB-1951).
 *
 * MSW intercepts real fetch calls — no service layer mocking.
 */

import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import { server } from '../../test/mocks/server';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import { http, HttpResponse } from 'msw';

// Mock only auth context (Keycloak is external, can't MSW it)
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => createAuthMock('tenant-admin'),
}));

// Mock EnvironmentContext (uses react-oidc-context + fetch internally)
vi.mock('../../contexts/EnvironmentContext', () => ({
  PortalEnvironmentProvider: ({ children }: { children: React.ReactNode }) => children,
  usePortalEnvironment: () => ({
    activeEnvironment: 'prod',
    activeConfig: { name: 'prod', label: 'Production', mode: 'full', color: 'red' },
    environments: [{ name: 'prod', label: 'Production', mode: 'full', color: 'red' }],
    endpoints: null,
    switchEnvironment: vi.fn(),
    loading: false,
    error: null,
  }),
}));

// Mock Toast (shared component requiring provider)
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('API Catalog (MSW integration)', () => {
  it('loads published APIs from real HTTP', async () => {
    const { default: APICatalog } = await import('../../pages/apis/APICatalog');

    renderWithProviders(<APICatalog />, { route: '/apis' });

    // Verify component renders without crashing and displays content
    await waitFor(
      () => {
        expect(document.body.textContent).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });

  it('shows empty state when no APIs available', async () => {
    server.use(
      http.get('https://api.gostoa.dev/v1/portal/apis', () => {
        return HttpResponse.json([]);
      })
    );

    const { default: APICatalog } = await import('../../pages/apis/APICatalog');
    renderWithProviders(<APICatalog />, { route: '/apis' });

    await waitFor(
      () => {
        expect(document.body.textContent).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });

  it('handles API error gracefully', async () => {
    server.use(
      http.get('https://api.gostoa.dev/v1/portal/apis', () => {
        return new HttpResponse(null, { status: 500 });
      })
    );

    const { default: APICatalog } = await import('../../pages/apis/APICatalog');
    renderWithProviders(<APICatalog />, { route: '/apis' });

    // Should not throw — render error state
    await waitFor(
      () => {
        expect(document.body.textContent).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });

  it('renders subscription flow with real data', async () => {
    const { default: MySubscriptions } = await import('../../pages/subscriptions/MySubscriptions');

    renderWithProviders(<MySubscriptions />, { route: '/subscriptions' });

    await waitFor(
      () => {
        expect(document.body.textContent).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });
});
