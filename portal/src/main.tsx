import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider as OidcProvider } from 'react-oidc-context';
import { WebStorageStateStore } from 'oidc-client-ts';
import { ThemeProvider } from '@stoa/shared/contexts';
import { ToastProvider } from '@stoa/shared/components/Toast';
import App from './App';
import { config } from './config';
import './index.css';

// Core Web Vitals monitoring can be added here if needed
// Example: send metrics to analytics service

// React Query client configuration
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000, // 30s (comme Console)
      gcTime: 30 * 60 * 1000, // 30min
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const oidcConfig = {
  authority: config.keycloak.authority,
  client_id: config.keycloak.clientId, // stoa-portal (different from control-plane-ui)
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  scope: 'openid profile email',
  automaticSilentRenew: true,
  // PKCE configuration - required by Keycloak 25+
  response_type: 'code',
  pkce_method: 'S256',
  // Persist tokens in localStorage for cross-tab session and faster boot
  userStore: new WebStorageStateStore({ store: window.localStorage }),
  onSigninCallback: () => {
    // Remove OIDC params from URL after successful login
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>
          <OidcProvider {...oidcConfig}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </OidcProvider>
        </QueryClientProvider>
      </ToastProvider>
    </ThemeProvider>
  </React.StrictMode>
);

// Smooth handoff: HTML splash → React app (double-rAF ensures React has painted)
requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    const splash = document.getElementById('stoa-splash');
    if (splash) {
      splash.classList.add('hide');
      splash.addEventListener('transitionend', () => splash.remove());
    }
  });
});
