/**
 * Seeded Test Fixture — extends test-base with DataSeeder (CAB-1990)
 *
 * Provides `dataSeeder` and `seededData` fixtures for tests that need
 * pre-populated data (APIs, MCP servers, subscriptions).
 *
 * Usage:
 *   import { test, expect } from '../fixtures/seeded-test';
 *
 *   test('dashboard shows seeded APIs', async ({ seededData, consolePage }) => {
 *     expect(seededData.apis).toHaveLength(3);
 *     // ... navigate and assert
 *   });
 */

import { test as baseTest, expect } from './test-base';
import { DataSeeder, SeededState } from './data-seeder';
import type { APIRequestContext } from '@playwright/test';

// ---------------------------------------------------------------------------
// Extended fixtures
// ---------------------------------------------------------------------------

export type SeededFixtures = {
  /** Raw DataSeeder instance — for manual seed/cleanup control */
  dataSeeder: DataSeeder;
  /** Auto-seeded data — created before test, cleaned up after */
  seededData: SeededState;
};

export const test = baseTest.extend<SeededFixtures>({
  /**
   * DataSeeder instance — use for manual control over seed lifecycle.
   * Does NOT auto-seed; call seeder.seed() yourself.
   */
  dataSeeder: async ({ playwright }, use) => {
    const request: APIRequestContext = await playwright.request.newContext();
    const seeder = new DataSeeder(request);
    await use(seeder);
    await request.dispose();
  },

  /**
   * Auto-seeded data — seeds before the test, cleans up after.
   * Each test gets a unique runId for isolation.
   */
  seededData: async ({ playwright }, use) => {
    const request: APIRequestContext = await playwright.request.newContext();
    const seeder = new DataSeeder(request);

    const runId = `e2e-${Date.now()}`;
    const state = await seeder.seed(runId);

    await use(state);

    // Cleanup after test
    await seeder.cleanup(state);
    await request.dispose();
  },
});

// Re-export expect and types for convenience
export { expect };
export type { SeededState, DataSeeder } from './data-seeder';
