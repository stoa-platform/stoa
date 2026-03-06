import { defineConfig } from '@playwright/test';

/**
 * Mocked smoke test config — runs against built Console app with API mocking.
 * No live backend required. Used in PR CI to catch UI regressions.
 */
export default defineConfig({
  testDir: '.',
  testMatch: '*.smoke.ts',
  fullyParallel: true,
  retries: 1,
  workers: 2,
  timeout: 30_000,
  reporter: [['list'], ['html', { open: 'never', outputFolder: '../test-results/smoke-mock' }]],
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run preview -- --port 4173',
    cwd: '../../control-plane-ui',
    port: 4173,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    env: {
      VITE_API_URL: 'http://localhost:4173/api',
      VITE_KEYCLOAK_URL: 'http://localhost:4173/auth',
      VITE_BASE_DOMAIN: 'localhost',
    },
  },
});
