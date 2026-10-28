import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const runtimeWindow = window as unknown as Record<string, unknown>;

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('VITE_TEST_GATEWAY_URL', '');
  vi.stubEnv('VITE_PORTAL_MODE', '');
  vi.stubEnv('VITE_API_URL', 'http://127.0.0.1:18000');
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
