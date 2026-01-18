import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider as OidcProvider } from 'react-oidc-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { config } from './config';
import './index.css';

// Create a client for React Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30000,
    },
  },
});

const oidcConfig = {
  authority: config.keycloak.authority,
  client_id: config.keycloak.clientId,
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  scope: 'openid profile email roles',
  automaticSilentRenew: true,
  // PKCE configuration - required by Keycloak 25+
  // response_type: 'code' triggers Authorization Code flow with PKCE
  response_type: 'code',
  // Explicitly require PKCE (S256 is the only secure option)
  // This ensures code_challenge and code_challenge_method are sent
  pkce_method: 'S256',
  onSigninCallback: () => {
    // Remove OIDC params from URL after successful login
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <OidcProvider {...oidcConfig}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </OidcProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
