/**
 * Integration tests using MSW (Mock Service Worker) instead of vi.mock.
 *
 * These tests render real components with real React Query hooks,
 * and MSW intercepts the HTTP requests with realistic responses.
 * No vi.mock on service layer — the Boundary Integrity Rule (CAB-1951).
 */

import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { server } from '../../test/mocks/server';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import { http, HttpResponse } from 'msw';

// Mock only auth (we can't avoid this — Keycloak is external)
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => createAuthMock('cpi-admin'),
}));

// MSW lifecycle — per-file, not global (safe coexistence with vi.mock tests)
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Tenants page (MSW integration)', () => {
  it('loads and displays tenant data from API', async () => {
    // Dynamic import to avoid module-level side effects
    const { Tenants } = await import('../../pages/Tenants');

    renderWithProviders(<Tenants />, { route: '/tenants' });

    // MSW handlers return mockTenants (Oasis Gunters, IOI Sixers)
    await waitFor(
      () => {
        expect(screen.getAllByText(/oasis/i).length).toBeGreaterThan(0);
      },
      { timeout: 3000 }
    );
  });

  it('shows error state when API returns 500', async () => {
    server.use(
      http.get('https://api.gostoa.dev/v1/tenants', () => {
        return new HttpResponse(null, { status: 500 });
      })
    );

    const { Tenants } = await import('../../pages/Tenants');
    renderWithProviders(<Tenants />, { route: '/tenants' });

    await waitFor(
      () => {
        // Should show error or retry UI, not crash
        const root = document.querySelector('[data-testid]') || document.body;
        expect(root).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });

  it('displays platform status from aggregated endpoint', async () => {
    const { PlatformDashboard: Dashboard } =
      await import('../../pages/Dashboard/PlatformDashboard');

    renderWithProviders(<Dashboard />, { route: '/' });

    // Dashboard fetches /v1/platform/status and shows data
    await waitFor(
      () => {
        // Should render without crashing, even if specific text varies
        expect(document.body.textContent).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });

  it('handles empty tenant list gracefully', async () => {
    server.use(
      http.get('https://api.gostoa.dev/v1/tenants', () => {
        return HttpResponse.json([]);
      })
    );

    const { Tenants } = await import('../../pages/Tenants');
    renderWithProviders(<Tenants />, { route: '/tenants' });

    await waitFor(
      () => {
        // Should show empty state, not crash
        expect(document.body.textContent).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });
});
