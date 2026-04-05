import { defineConfig, devices } from '@playwright/test';

/**
 * Visual regression config — golden baseline comparison (CAB-1994)
 *
 * Run in Docker for pixel-consistent baselines:
 *   docker run --rm -v $(pwd):/work -w /work mcr.microsoft.com/playwright:v1.58.2-jammy \
 *     npx playwright test --config=visual/playwright.config.ts
 *
 * Update baselines:
 *   docker run ... --update-snapshots
 */
export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  fullyParallel: true,
  retries: process.env.CI ? 0 : 1,
  workers: 1, // sequential for stable screenshots
  timeout: 30_000,

  snapshotDir: '../golden',
  snapshotPathTemplate: '{snapshotDir}/{projectName}/{arg}{ext}',

  reporter: [['list'], ['html', { open: 'never', outputFolder: '../test-results/visual' }]],

  expect: {
    toHaveScreenshot: {
      threshold: 0.2,
      maxDiffPixelRatio: 0.002,
    },
  },

  use: {
    viewport: { width: 1280, height: 900 },
    colorScheme: 'light',
    screenshot: 'off', // we take explicit screenshots via toHaveScreenshot
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'console-visual',
      testMatch: /console-visual\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:4173',
      },
    },
    {
      name: 'portal-visual',
      testMatch: /portal-visual\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:4174',
      },
    },
  ],

  webServer: [
    {
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
    {
      command: 'npm run preview -- --port 4174',
      cwd: '../../portal',
      port: 4174,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: {
        VITE_API_URL: 'http://localhost:4174/api',
        VITE_KEYCLOAK_URL: 'http://localhost:4174/auth',
        VITE_BASE_DOMAIN: 'localhost',
      },
    },
  ],
});
