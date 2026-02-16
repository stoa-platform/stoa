import { describe, it, expect, vi, beforeEach } from 'vitest';

// Helper to re-import config with fresh env vars
async function importConfig() {
  vi.resetModules();
  const mod = await import('./config');
  return mod;
}

beforeEach(() => {
  vi.resetModules();
  // Clear all VITE_ env vars
  vi.stubEnv('VITE_BASE_DOMAIN', '');
  vi.stubEnv('VITE_ENVIRONMENT', '');
  vi.stubEnv('VITE_APP_TITLE', '');
  vi.stubEnv('VITE_API_URL', '');
  vi.stubEnv('VITE_KEYCLOAK_URL', '');
  vi.stubEnv('VITE_KEYCLOAK_REALM', '');
  vi.stubEnv('VITE_KEYCLOAK_CLIENT_ID', '');
  vi.stubEnv('VITE_GATEWAY_URL', '');
  vi.stubEnv('VITE_MCP_GATEWAY_URL', '');
  vi.stubEnv('VITE_AWX_URL', '');
  vi.stubEnv('VITE_PORTAL_URL', '');
  vi.stubEnv('VITE_ENABLE_MONITORING', '');
  vi.stubEnv('VITE_ENABLE_GITOPS', '');
  vi.stubEnv('VITE_ENABLE_DEBUG', '');
});

describe('config', () => {
  it('uses default base domain gostoa.dev', async () => {
    const { config } = await importConfig();
    expect(config.app.baseDomain).toBe('gostoa.dev');
  });

  it('constructs API URL from base domain', async () => {
    const { config } = await importConfig();
    expect(config.api.baseUrl).toBe('https://api.gostoa.dev');
    expect(config.api.docsUrl).toBe('https://api.gostoa.dev/docs');
  });

  it('constructs keycloak authority from url and realm', async () => {
    const { config } = await importConfig();
    expect(config.keycloak.url).toBe('https://auth.gostoa.dev');
    expect(config.keycloak.realm).toBe('stoa');
    expect(config.keycloak.clientId).toBe('control-plane-ui');
    expect(config.keycloak.authority).toBe('https://auth.gostoa.dev/realms/stoa');
  });

  it('constructs service URLs from base domain', async () => {
    const { config } = await importConfig();
    expect(config.services.gateway.url).toBe('https://gateway.gostoa.dev');
    expect(config.services.gateway.consoleUrl).toBe('https://gateway.gostoa.dev/apigatewayui/');
    expect(config.services.mcpGateway.url).toBe('https://mcp.gostoa.dev');
    expect(config.services.awx.url).toBe('https://awx.gostoa.dev');
    expect(config.services.portal.url).toBe('https://portal.gostoa.dev');
  });

  it('constructs AWX job URL correctly', async () => {
    const { config } = await importConfig();
    expect(config.services.awx.getJobUrl(42)).toBe('https://awx.gostoa.dev/#/jobs/playbook/42');
  });

  it('constructs GitLab URLs correctly', async () => {
    const { config } = await importConfig();
    expect(config.services.gitlab.getProjectUrl('123')).toBe('https://gitlab.com/projects/123');
    expect(config.services.gitlab.getRepoUrl('stoa/api')).toBe('https://gitlab.com/stoa/api');
  });

  it('constructs ArgoCD app URL correctly', async () => {
    const { config } = await importConfig();
    expect(config.services.argocd.getAppUrl('stoa-gateway')).toBe(
      'https://argocd.gostoa.dev/applications/stoa-gateway'
    );
  });

  it('defaults feature flags correctly', async () => {
    const { config } = await importConfig();
    expect(config.features.enableMonitoring).toBe(true);
    expect(config.features.enableGitOps).toBe(true);
    expect(config.features.enableDebug).toBe(false);
    expect(config.features.enableApplications).toBe(true);
    expect(config.features.enableAITools).toBe(true);
  });

  it('defaults UI configuration', async () => {
    const { config } = await importConfig();
    expect(config.ui.itemsPerPage).toBe(20);
    expect(config.ui.refreshInterval).toBe(30000);
    expect(config.ui.dateFormat).toBe('YYYY-MM-DD HH:mm:ss');
  });

  it('defaults app metadata', async () => {
    const { config } = await importConfig();
    expect(config.app.title).toBe('STOA Control Plane');
    expect(config.app.environment).toBe('production');
    expect(config.app.isDev).toBe(false);
  });

  it('exports quickLinks array', async () => {
    const { quickLinks } = await importConfig();
    expect(quickLinks).toHaveLength(3);
    expect(quickLinks[0].name).toBe('API Documentation');
    expect(quickLinks[1].name).toBe('Gateway Console');
    expect(quickLinks[2].name).toBe('AWX Automation');
  });
});
