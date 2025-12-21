import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider as OidcProvider } from 'react-oidc-context';
import App from './App';
import './index.css';

const oidcConfig = {
  authority: import.meta.env.VITE_KEYCLOAK_URL
    ? `${import.meta.env.VITE_KEYCLOAK_URL}/realms/${import.meta.env.VITE_KEYCLOAK_REALM || 'apim'}`
    : 'https://auth.apim.cab-i.com/realms/apim',
  client_id: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'control-plane-ui',
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  scope: 'openid profile email',
  automaticSilentRenew: true,
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
