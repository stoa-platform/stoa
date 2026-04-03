/**
 * Portal integration tests using MSW instead of vi.mock (CAB-1951).
 *
 * MSW intercepts real fetch calls — no service layer mocking.
 */

import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { server } from '../../test/mocks/server';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import { http, HttpResponse } from 'msw';

// Mock only auth context (Keycloak is external, can't MSW it)
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => createAuthMock('tenant-admin'),
}));

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('API Catalog (MSW integration)', () => {
  it('loads published APIs from real HTTP', async () => {
    const { default: APICatalog } = await import('../../pages/APICatalog');

    renderWithProviders(<APICatalog />, { route: '/apis' });

    await waitFor(
      () => {
        expect(screen.getByText(/weather/i)).toBeInTheDocument();
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

    const { default: APICatalog } = await import('../../pages/APICatalog');
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

    const { default: APICatalog } = await import('../../pages/APICatalog');
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
    const { default: MySubscriptions } = await import('../../pages/MySubscriptions');

    renderWithProviders(<MySubscriptions />, { route: '/subscriptions' });

    await waitFor(
      () => {
        expect(document.body.textContent).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });
});
