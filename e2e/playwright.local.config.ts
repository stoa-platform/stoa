/**
 * Playwright config for local standalone tests (non-BDD).
 * Usage: npx playwright test --config playwright.local.config.ts
 */
import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';

// Load .env.local first, fallback to .env
dotenv.config({ path: '.env.local' });
dotenv.config();

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 10000 },

  reporter: [
    ['html', { outputFolder: 'reports/local', open: 'never' }],
    ['json', { outputFile: 'reports/local/results.json' }],
    ['list'],
  ],

  use: {
    baseURL: process.env.STOA_CONSOLE_URL || 'http://console.stoa.local',
    trace: 'on',
    screenshot: 'on',
    video: 'on',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },

  projects: [
    {
      name: 'local',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /local-.*\.spec\.ts/,
    },
  ],
});
