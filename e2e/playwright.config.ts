import { defineConfig, devices } from '@playwright/test';
import { defineBddConfig } from 'playwright-bdd';
import * as dotenv from 'dotenv';

dotenv.config();

const testDir = defineBddConfig({
  features: 'features/**/*.feature',
  steps: 'steps/**/*.ts',
  importTestFrom: 'fixtures/test-base.ts',
});

export default defineConfig({
  testDir,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 60000,
  expect: {
    timeout: 10000,
  },

  reporter: [
    ['html', { outputFolder: 'reports/html', open: 'never' }],
    ['json', { outputFile: 'reports/results.json' }],
    ['list'],
    ...(process.env.CI ? [['github'] as const] : []),
  ],

  use: {
    baseURL: process.env.STOA_PORTAL_URL || 'https://portal.stoa.cab-i.com',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },

  projects: [
    // Auth setup - runs first to create storage states for all personas
    {
      name: 'auth-setup',
      testMatch: /auth\.setup\.ts/,
      use: {
        headless: true,
      },
    },

    // Portal tests
    {
      name: 'portal-chromium',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.STOA_PORTAL_URL || 'https://portal.stoa.cab-i.com',
        storageState: 'fixtures/.auth/parzival.json',
      },
      dependencies: ['auth-setup'],
      testMatch: /portal/,
    },

    // Console tests
    {
      name: 'console-chromium',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.STOA_CONSOLE_URL || 'https://console.stoa.cab-i.com',
        storageState: 'fixtures/.auth/parzival.json',
      },
      dependencies: ['auth-setup'],
      testMatch: /console/,
    },

    // Gateway API tests (no browser, just HTTP)
    {
      name: 'gateway',
      use: {
        baseURL: process.env.STOA_GATEWAY_URL || 'https://api.stoa.cab-i.com',
      },
      testMatch: /gateway/,
    },
  ],

  // Global setup/teardown if needed
  // globalSetup: require.resolve('./fixtures/global-setup.ts'),
  // globalTeardown: require.resolve('./fixtures/global-teardown.ts'),
});
