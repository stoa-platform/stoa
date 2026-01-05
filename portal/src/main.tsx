import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider as OidcProvider } from 'react-oidc-context';
import App from './App';
import { config } from './config';
import './index.css';

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
  onSigninCallback: () => {
    // Remove OIDC params from URL after successful login
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OidcProvider {...oidcConfig}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </OidcProvider>
  </React.StrictMode>
);
