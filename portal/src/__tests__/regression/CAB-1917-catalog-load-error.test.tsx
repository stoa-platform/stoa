/**
 * CAB-1917: a failed portal catalog request must surface as an error.
 * A resolved empty page is only the genuine empty catalog.
 */

import { type ReactNode } from 'react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';

import { APICatalog } from '../../pages/apis/APICatalog';
import { useAPIs } from '../../hooks/useAPIs';
import i18n from '../../i18n';
import { server } from '../../test/mocks/server';
import { createAuthMock, renderWithProviders } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => createAuthMock('tenant-admin'),
}));

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

const CATALOG_URL = 'https://api.gostoa.dev/v1/portal/apis';

function emptyCatalog() {
  return HttpResponse.json({ apis: [], total: 0, page: 1, page_size: 20 });
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  i18n.addResourceBundle(
    'en',
    'catalog',
    {
      title: 'API Catalog',
      subtitle: 'Browse and discover available APIs',
      failedToLoad: 'Failed to load APIs',
      tryAgain: 'Try Again',
      noApisFound: 'No APIs Found',
      noApisYet: 'There are no published APIs available yet. Check back later!',
      loadingApis: 'Loading APIs...',
      gridView: 'Grid view',
      listView: 'List view',
      refresh: 'Refresh',
    },
    true,
    true
  );
});

describe('regression/CAB-1917 catalog load error', () => {
  it('keeps a successful catalog visible', async () => {
    renderWithProviders(<APICatalog />, { route: '/apis' });

    expect(await screen.findByRole('list', { name: 'API catalog' })).toBeInTheDocument();
    expect(screen.getByText('weather-api')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Failed to load APIs' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'No APIs Found' })).not.toBeInTheDocument();
  });

  it('shows the empty catalog state when the server returns no APIs', async () => {
    server.use(http.get(CATALOG_URL, () => emptyCatalog()));

    renderWithProviders(<APICatalog />, { route: '/apis' });

    expect(await screen.findByRole('heading', { name: 'No APIs Found' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Failed to load APIs' })).not.toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'API catalog' })).not.toBeInTheDocument();
  });

  it('shows the catalog error state on HTTP 500 instead of an empty list', async () => {
    server.use(http.get(CATALOG_URL, () => new HttpResponse(null, { status: 500 })));

    renderWithProviders(<APICatalog />, { route: '/apis' });

    expect(await screen.findByRole('heading', { name: 'Failed to load APIs' })).toBeInTheDocument();
    expect(
      screen.getByText('Something went wrong on our end. Please try again later.')
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try Again' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'No APIs Found' })).not.toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'API catalog' })).not.toBeInTheDocument();
  });

  it('shows the catalog error state when the network request fails', async () => {
    server.use(http.get(CATALOG_URL, () => HttpResponse.error()));

    renderWithProviders(<APICatalog />, { route: '/apis' });

    expect(await screen.findByRole('heading', { name: 'Failed to load APIs' })).toBeInTheDocument();
    expect(
      screen.getByText('Unable to connect to the server. Please check your connection.')
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'No APIs Found' })).not.toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'API catalog' })).not.toBeInTheDocument();
  });

  it('exposes the 500 to useAPIs instead of a successful empty page', async () => {
    server.use(http.get(CATALOG_URL, () => new HttpResponse(null, { status: 500 })));
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });

    function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useAPIs(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.isSuccess).toBe(false);
    expect(result.current.data).toBeUndefined();
  });
});
