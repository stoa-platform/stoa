import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const runtimeWindow = window as unknown as Record<string, unknown>;

beforeEach(() => {
  vi.resetModules();
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
    const { config, APP_VERSION_MARK } = await import('./config');
    expect(config.app.version).toBe('0.0.0-dev');
    expect(config.app.versionMark).toBe('stoa-app-version:0.0.0-dev');
    expect(APP_VERSION_MARK).toBe('stoa-app-version:0.0.0-dev');
  });

  it('uses VITE_APP_VERSION when set', async () => {
    vi.stubEnv('VITE_APP_VERSION', '1.4.0');
    const { config, APP_VERSION_MARK } = await import('./config');
    expect(config.app.version).toBe('1.4.0');
    expect(config.app.versionMark).toBe('stoa-app-version:1.4.0');
    expect(APP_VERSION_MARK).toBe('stoa-app-version:1.4.0');
  });
});
