/**
 * Playwright config for STOA Gateway Audit (CAB-1969 MEGA)
 *
 * Targets docker-compose local stack (localhost).
 * No BDD — pure spec files in e2e/tests/audit-*.spec.ts
 *
 * Usage:
 *   cd e2e && npx playwright test --config playwright.audit.config.ts
 *   cd e2e && npx playwright test --config playwright.audit.config.ts audit-phase1
 */
import { defineConfig, devices } from '@playwright/test';

const API_URL = process.env.STOA_API_URL || 'http://localhost:8000';
const CONSOLE_URL = process.env.STOA_CONSOLE_URL || 'http://localhost:3000';
const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'http://localhost:8081';

export default defineConfig({
  testDir: './tests',
  testMatch: /audit-phase.*\.spec\.ts/,
  fullyParallel: false, // phases run sequentially
  retries: 0,
  workers: 1, // sequential for audit reliability
  timeout: 60_000,
  expect: { timeout: 10_000 },

  reporter: [
    ['html', { outputFolder: 'test-results/audit/report', open: 'never' }],
    ['json', { outputFile: 'test-results/audit/results.json' }],
    ['list'],
  ],

  outputDir: 'test-results/audit/artifacts',

  use: {
    baseURL: CONSOLE_URL,
    trace: 'on',
    screenshot: 'on',
    video: 'off',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    // No extraHTTPHeaders — custom headers break CORS preflight with Keycloak
  },

  projects: [
    {
      name: 'audit-infra',
      testMatch: /audit-phase1-infra\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'audit-mcp',
      testMatch: /audit-phase2-mcp\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['audit-infra'],
    },
    {
      name: 'audit-security',
      testMatch: /audit-phase3-security\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'audit-observability',
      testMatch: /audit-phase4-observability\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['audit-security'],
    },
    {
      name: 'audit-guardrails',
      testMatch: /audit-phase5-guardrails\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'audit-deploy',
      testMatch: /audit-phase6-deploy\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['audit-guardrails'],
    },
  ],

  // Environment variables available in tests
  metadata: {
    API_URL,
    CONSOLE_URL,
    GATEWAY_URL,
  },
});
