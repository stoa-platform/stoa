import { defineConfig, devices } from '@playwright/test';
import { defineBddConfig } from 'playwright-bdd';
import * as dotenv from 'dotenv';

dotenv.config();

const testDir = defineBddConfig({
  features: 'features/**/*.feature',
  steps: 'steps/**/*.ts',
  importTestFrom: 'fixtures/test-base.ts',
  tags: 'not @wip',
});

export default defineConfig({
  testDir,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
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
    baseURL: process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev',
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
      testDir: './fixtures',
      testMatch: /auth\.setup\.ts/,
      use: {
        headless: true,
      },
    },

    // TTFTC test — Alex Freelance fresh onboarding (no pre-auth)
    {
      name: 'ttftc',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev',
      },
      dependencies: ['auth-setup'],
      testMatch: /alex-ttftc/,
    },

    // Portal tests
    {
      name: 'portal-chromium',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev',
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
        baseURL: process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev',
        storageState: 'fixtures/.auth/parzival.json',
      },
      dependencies: ['auth-setup'],
      testMatch: /console/,
    },

    // Gateway API tests (no browser, just HTTP)
    // testMatch must NOT match console-gateways — those are browser tests needing auth
    {
      name: 'gateway',
      use: {
        baseURL: process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev',
      },
      testMatch: /gateway-access/,
    },
  ],

  // Global setup/teardown if needed
  // globalSetup: require.resolve('./fixtures/global-setup.ts'),
  // globalTeardown: require.resolve('./fixtures/global-teardown.ts'),
});
