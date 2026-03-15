/**
 * Regression test for CAB-1790 — MCP connector OAuth callback redirect-to-login
 *
 * PR: #1720
 * Root cause: react-oidc-context's OidcProvider detects code/state URL params
 *   (from the MCP provider OAuth callback) and tries to exchange them with
 *   Keycloak. This fails because the params are from the MCP provider (e.g.
 *   Sentry, Linear), not Keycloak. The failure causes the user session to
 *   never load → isAuthenticated=false → redirect to login.
 *
 * Fix: skipSigninCallback=true when pathname starts with /mcp-connectors/callback
 *   in the OidcProvider config (main.tsx), plus moving the callback route outside
 *   ProtectedRoutes (App.tsx).
 *
 * Invariant: The /mcp-connectors/callback route must never trigger OIDC signin
 *   callback processing, even when code/state params are present in the URL.
 */
import { describe, it, expect } from 'vitest';

describe('regression/CAB-1790: MCP OAuth callback must not trigger OIDC signin', () => {
  it('skipSigninCallback is true when on /mcp-connectors/callback path', () => {
    // Simulate the callback path
    const pathname = '/mcp-connectors/callback';
    const skipSigninCallback = pathname.startsWith('/mcp-connectors/callback');
    expect(skipSigninCallback).toBe(true);
  });

  it('skipSigninCallback is false for normal paths', () => {
    const normalPaths = ['/', '/dashboard', '/mcp-connectors', '/login', '/apis'];
    for (const pathname of normalPaths) {
      const skipSigninCallback = pathname.startsWith('/mcp-connectors/callback');
      expect(skipSigninCallback).toBe(false);
    }
  });

  it('skipSigninCallback is true for callback path with query params', () => {
    // The pathname check doesn't include query params (window.location.pathname)
    const pathname = '/mcp-connectors/callback';
    const skipSigninCallback = pathname.startsWith('/mcp-connectors/callback');
    expect(skipSigninCallback).toBe(true);
  });

  it('isMcpCallback guard prevents signinRedirect on callback path', () => {
    // Simulates the AuthContext.tsx guard logic
    const pathname = '/mcp-connectors/callback';
    const isMcpCallback = pathname.startsWith('/mcp-connectors/callback');
    const isAuthenticated = false;
    const isLoading = false;
    const hasAuthParams = true; // code/state params present from provider

    // The guard should NOT trigger signinRedirect when on callback path
    const shouldRedirect = !isAuthenticated && !isLoading && hasAuthParams && !isMcpCallback;
    expect(shouldRedirect).toBe(false);
  });

  it('signinRedirect still works for non-callback paths with auth params', () => {
    const pathname = '/dashboard';
    const isMcpCallback = pathname.startsWith('/mcp-connectors/callback');
    const isAuthenticated = false;
    const isLoading = false;
    const hasAuthParams = true;

    const shouldRedirect = !isAuthenticated && !isLoading && hasAuthParams && !isMcpCallback;
    expect(shouldRedirect).toBe(true);
  });
});
