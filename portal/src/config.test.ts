import fs from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

const runtimeWindow = window as unknown as Record<string, unknown>;

beforeEach(() => {
  vi.resetModules();
  mockLoadEnv.mockReset();
  mockLoadEnv.mockReturnValue({});
  vi.stubEnv('VITE_TEST_GATEWAY_URL', '');
  vi.stubEnv('VITE_PORTAL_MODE', '');
  vi.stubEnv('VITE_API_URL', 'http://127.0.0.1:18000');
  vi.stubEnv('VITE_APP_VERSION', '');
  delete runtimeWindow.__STOA_RUNTIME__;
});

afterEach(() => {
  delete runtimeWindow.__STOA_RUNTIME__;
  vi.unstubAllEnvs();
});

describe('private testing gateway runtime config', () => {
  it('keeps the existing default mode and has no gateway override when unset', async () => {
    const { config } = await import('./config');
    expect(config.testing.gatewayBaseUrl).toBe('');
    expect(config.portalMode).toBe('production');
  });

  it('reads the private runtime override independently from the control-plane URL', async () => {
    vi.stubEnv('VITE_TEST_GATEWAY_URL', 'https://build.example.test');
    runtimeWindow.__STOA_RUNTIME__ = {
      VITE_TEST_GATEWAY_URL: '/api',
      VITE_PORTAL_MODE: 'non-production',
    };
    const { config } = await import('./config');
    expect(config.testing.gatewayBaseUrl).toBe('/api');
    expect(config.portalMode).toBe('non-production');
    expect(config.api.baseUrl).toBe('http://127.0.0.1:18000');
  });
});

describe('application version', () => {
  it('falls back to 0.0.0-dev when VITE_APP_VERSION is unset', async () => {
    const { config } = await import('./config');
    expect(config.app.version).toBe('0.0.0-dev');
  });

  it('falls back to 0.0.0-dev when VITE_APP_VERSION is whitespace', async () => {
    vi.stubEnv('VITE_APP_VERSION', '   ');
    const { config } = await import('./config');
    expect(config.app.version).toBe('0.0.0-dev');
  });

  it('uses VITE_APP_VERSION when set', async () => {
    vi.stubEnv('VITE_APP_VERSION', '1.4.0');
    const { config } = await import('./config');
    expect(config.app.version).toBe('1.4.0');
  });

  it('trims surrounding whitespace from VITE_APP_VERSION', async () => {
    vi.stubEnv('VITE_APP_VERSION', '  1.4.0  ');
    const { config } = await import('./config');
    expect(config.app.version).toBe('1.4.0');
  });
});

describe('vite resolveAppVersion', () => {
  function withPackageJson(pkg: Record<string, unknown>, fn: (dir: string) => void) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'portal-version-'));
    try {
      fs.writeFileSync(path.join(dir, 'package.json'), JSON.stringify(pkg));
      fn(dir);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }

  it('skips blank env values in the Vitest branch and falls back to 0.0.0-dev', () => {
    expect(resolveAppVersion('test', { env: { VITEST: 'true', VITE_APP_VERSION: '   ' } })).toBe(
      '0.0.0-dev',
    );
    expect(
      resolveAppVersion('test', {
        env: { VITEST: 'true', VITE_APP_VERSION: '   ', APP_VERSION: ' 2.1.0 ' },
      }),
    ).toBe('2.1.0');
    expect(
      resolveAppVersion('test', {
        env: { VITEST: 'true', VITE_APP_VERSION: '', APP_VERSION: '   ' },
      }),
    ).toBe('0.0.0-dev');
  });

  it('skips blank VITE_APP_VERSION and APP_VERSION before reading package.json', () => {
    withPackageJson({ version: ' 1.4.0 ' }, (pkgDir) => {
      mockLoadEnv.mockReturnValueOnce({ VITE_APP_VERSION: '   ' });
      expect(
        resolveAppVersion('production', {
          env: { VITE_APP_VERSION: '   ', APP_VERSION: '  ' },
          pkgDir,
        }),
      ).toBe('1.4.0');
      expect(mockLoadEnv).toHaveBeenLastCalledWith('production', pkgDir, 'VITE_');

      mockLoadEnv.mockReturnValueOnce({});
      expect(
        resolveAppVersion('production', {
          env: { VITE_APP_VERSION: '   ', APP_VERSION: ' 2.4.0 ' },
          pkgDir,
        }),
      ).toBe('2.4.0');

      mockLoadEnv.mockReturnValueOnce({ VITE_APP_VERSION: ' 3.1.0 ' });
      expect(
        resolveAppVersion('production', {
          env: { VITE_APP_VERSION: '   ' },
          pkgDir,
        }),
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
          }),
        ).toBe('0.0.0-dev');
      });
    }
  });
});
