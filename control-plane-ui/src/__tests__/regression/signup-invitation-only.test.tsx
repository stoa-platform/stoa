import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useLocation } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { renderWithProviders } from '../../test/helpers';
import App from '../../App';

const { oidc } = vi.hoisted(() => ({
  oidc: {
    isAuthenticated: false,
    isLoading: false,
    user: null,
    signinRedirect: vi.fn(),
    signinSilent: vi.fn(),
    signoutRedirect: vi.fn(),
  },
}));

vi.mock('react-oidc-context', () => ({
  useAuth: () => oidc,
  hasAuthParams: () => false,
}));

const requests: string[] = [];
const server = setupServer(
  http.all('*', ({ request }) => {
    requests.push(`${request.method} ${new URL(request.url).pathname}`);
    return HttpResponse.json({});
  })
);

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="current-location">{location.pathname}</output>;
}

describe('console signup access', () => {
  beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
  afterAll(() => server.close());
  beforeEach(() => {
    vi.clearAllMocks();
    requests.length = 0;
    oidc.signinRedirect.mockResolvedValue(undefined);
  });
  afterEach(() => server.resetHandlers());

  it.each(['/signup', '/signup?mode=open'])(
    'redirects anonymous %s to login without creating an account',
    async (route) => {
      renderWithProviders(
        <>
          <App />
          <LocationProbe />
        </>,
        { route }
      );

      await waitFor(() =>
        expect(screen.getByTestId('current-location')).toHaveTextContent('/login')
      );
      const login = screen.getByRole('button', { name: 'Login with Keycloak' });
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
      expect(oidc.signinRedirect).not.toHaveBeenCalled();
      expect(requests).toEqual([]);

      await userEvent.click(login);

      expect(oidc.signinRedirect).toHaveBeenCalledExactlyOnceWith();
      expect(requests).toEqual([]);
    }
  );

  it.each(['/signup', '/signup?mode=open'])(
    'explains invitation-only access for %s while preserving login',
    async (route) => {
      const { container } = renderWithProviders(
        <>
          <App />
          <LocationProbe />
        </>,
        { route }
      );

      expect(
        await screen.findByText('Access is by invitation only. Ask an administrator for access.')
      ).toBeVisible();
      expect(screen.getByTestId('current-location')).toHaveTextContent('/login');
      expect(container.querySelector('form, input, textarea, select')).toBeNull();
      expect(screen.queryByRole('button', { name: /sign up|create account/i })).toBeNull();
      expect(oidc.signinRedirect).not.toHaveBeenCalled();
      expect(requests).toEqual([]);

      await userEvent.click(screen.getByRole('button', { name: 'Login with Keycloak' }));

      expect(oidc.signinRedirect).toHaveBeenCalledExactlyOnceWith();
      expect(requests).toEqual([]);
    }
  );
});
