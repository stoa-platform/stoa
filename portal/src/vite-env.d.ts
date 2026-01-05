/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BASE_DOMAIN: string;
  readonly VITE_ENVIRONMENT: string;
  readonly VITE_APP_TITLE: string;
  readonly VITE_APP_VERSION: string;
  readonly VITE_MCP_URL: string;
  readonly VITE_API_URL: string;
  readonly VITE_KEYCLOAK_URL: string;
  readonly VITE_KEYCLOAK_REALM: string;
  readonly VITE_KEYCLOAK_CLIENT_ID: string;
  readonly VITE_CONSOLE_URL: string;
  readonly VITE_DOCS_URL: string;
  readonly VITE_ENABLE_MCP_TOOLS: string;
  readonly VITE_ENABLE_SUBSCRIPTIONS: string;
  readonly VITE_ENABLE_API_CATALOG: string;
  readonly VITE_ENABLE_DEBUG: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
