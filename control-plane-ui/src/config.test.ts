import fs from 'fs';
import os from 'os';
import path from 'path';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockLoadEnv } = vi.hoisted(() => ({
  mockLoadEnv: vi.fn<(...args: unknown[]) => Record<string, string>>(() => ({})),
}));

vi.mock('vite', () => ({
  defineConfig: (cfg: unknown) => cfg,
  loadEnv: (...args: unknown[]) => mockLoadEnv(...args),
}));

vi.mock('@vitejs/plugin-react', () => ({
  default: () => ({ name: 'mock-react' }),
}));

import { resolveAppVersion } from '../vite.config';

// Helper to re-import config with fresh env vars
async function importConfig() {
  vi.resetModules();
  const mod = await import('./config');
  return mod;
}

beforeEach(() => {
  vi.resetModules();
  mockLoadEnv.mockReset();
  mockLoadEnv.mockReturnValue({});
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
  vi.stubEnv('VITE_GIT_PROVIDER', '');
  vi.stubEnv('VITE_GIT_REPO_URL', '');
  vi.stubEnv('VITE_APP_VERSION', '');
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
    expect(config.services.gateway.url).toBe('https://vps-wm.gostoa.dev');
    expect(config.services.gateway.consoleUrl).toBe('https://vps-wm.gostoa.dev/apigatewayui/');
    expect(config.services.mcpGateway.url).toBe('https://mcp.gostoa.dev');
    expect(config.services.awx.url).toBe('https://awx.gostoa.dev');
    expect(config.services.portal.url).toBe('https://portal.gostoa.dev');
  });

  it('constructs AWX job URL correctly', async () => {
    const { config } = await importConfig();
    expect(config.services.awx.getJobUrl(42)).toBe('https://awx.gostoa.dev/#/jobs/playbook/42');
  });

  it('constructs Git repository URLs correctly (default gitlab)', async () => {
    const { config } = await importConfig();
    expect(config.services.git.provider).toBe('gitlab');
    expect(config.services.git.label).toBe('GitLab');
    expect(config.services.git.url).toBe('https://gitlab.com');
    expect(config.services.git.webhookPath).toBe('webhooks/gitlab');
    expect(config.services.git.getProjectUrl('123')).toBe('https://gitlab.com/projects/123');
    expect(config.services.git.getRepoUrl('stoa/api')).toBe('https://gitlab.com/stoa/api');
  });

  it('switches to GitHub when VITE_GIT_PROVIDER=github', async () => {
    vi.stubEnv('VITE_GIT_PROVIDER', 'github');
    const { config } = await importConfig();
    expect(config.services.git.provider).toBe('github');
    expect(config.services.git.label).toBe('GitHub');
    expect(config.services.git.url).toBe('https://github.com');
    expect(config.services.git.webhookPath).toBe('webhooks/github');
  });

  it('uses custom VITE_GIT_REPO_URL when set', async () => {
    vi.stubEnv('VITE_GIT_PROVIDER', 'github');
    vi.stubEnv('VITE_GIT_REPO_URL', 'https://github.example.com');
    const { config } = await importConfig();
    expect(config.services.git.url).toBe('https://github.example.com');
    expect(config.services.git.label).toBe('GitHub');
  });

  it('preserves backward-compatible gitlab alias', async () => {
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

describe('application version', () => {
  it('falls back to 0.0.0-dev when VITE_APP_VERSION is unset', async () => {
    const { config } = await importConfig();
    expect(config.app.version).toBe('0.0.0-dev');
  });

  it('falls back to 0.0.0-dev when VITE_APP_VERSION is whitespace', async () => {
    vi.stubEnv('VITE_APP_VERSION', '   ');
    const { config } = await importConfig();
    expect(config.app.version).toBe('0.0.0-dev');
  });

  it('uses VITE_APP_VERSION when set', async () => {
    vi.stubEnv('VITE_APP_VERSION', '1.13.0');
    const { config } = await importConfig();
    expect(config.app.version).toBe('1.13.0');
  });

  it('trims surrounding whitespace from VITE_APP_VERSION', async () => {
    vi.stubEnv('VITE_APP_VERSION', '  1.13.0  ');
    const { config } = await importConfig();
    expect(config.app.version).toBe('1.13.0');
  });
});

describe('vite resolveAppVersion', () => {
  function withPackageJson(pkg: Record<string, unknown>, fn: (dir: string) => void) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'console-version-'));
    try {
      fs.writeFileSync(path.join(dir, 'package.json'), JSON.stringify(pkg));
      fn(dir);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }

  it('skips blank env values in the Vitest branch and falls back to 0.0.0-dev', () => {
    expect(resolveAppVersion('test', { env: { VITEST: 'true', VITE_APP_VERSION: '   ' } })).toBe(
      '0.0.0-dev'
    );
    expect(
      resolveAppVersion('test', {
        env: { VITEST: 'true', VITE_APP_VERSION: '   ', APP_VERSION: ' 2.1.0 ' },
      })
    ).toBe('2.1.0');
    expect(
      resolveAppVersion('test', {
        env: { VITEST: 'true', VITE_APP_VERSION: '', APP_VERSION: '   ' },
      })
    ).toBe('0.0.0-dev');
  });

  it('skips blank VITE_APP_VERSION and APP_VERSION before reading package.json', () => {
    withPackageJson({ version: ' 1.13.0 ' }, (pkgDir) => {
      mockLoadEnv.mockReturnValueOnce({ VITE_APP_VERSION: '   ' });
      expect(
        resolveAppVersion('production', {
          env: { VITE_APP_VERSION: '   ', APP_VERSION: '  ' },
          pkgDir,
        })
      ).toBe('1.13.0');
      expect(mockLoadEnv).toHaveBeenLastCalledWith('production', pkgDir, 'VITE_');

      mockLoadEnv.mockReturnValueOnce({});
      expect(
        resolveAppVersion('production', {
          env: { VITE_APP_VERSION: '   ', APP_VERSION: ' 2.4.0 ' },
          pkgDir,
        })
      ).toBe('2.4.0');

      mockLoadEnv.mockReturnValueOnce({ VITE_APP_VERSION: ' 3.1.0 ' });
      expect(
        resolveAppVersion('production', {
          env: { VITE_APP_VERSION: '   ' },
          pkgDir,
        })
      ).toBe('3.1.0');
    });
  });

  it('falls back to 0.0.0-dev when package.json version is missing, null, or whitespace', () => {
    for (const pkg of [{}, { version: null }, { version: '' }, { version: '   \t ' }]) {
      withPackageJson(pkg, (pkgDir) => {
        expect(
          resolveAppVersion('production', {
            env: { VITE_APP_VERSION: '', APP_VERSION: '   ' },
            pkgDir,
          })
        ).toBe('0.0.0-dev');
      });
    }
  });
});
