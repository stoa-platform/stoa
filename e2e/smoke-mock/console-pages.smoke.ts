import { test, expect } from '@playwright/test';
import { setupMockRoutes, injectMockAuth } from './mock-routes';

/**
 * Mocked Console smoke tests — 10 page-load checks.
 * Verifies pages render without errors using mocked API responses.
 * No live backend required.
 */

test.beforeEach(async ({ page }) => {
  await setupMockRoutes(page);
  await injectMockAuth(page);
});

test('Operations Dashboard loads', async ({ page }) => {
  await page.goto('/operations');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('My Usage page loads', async ({ page }) => {
  await page.goto('/my-usage');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('Business Analytics page loads', async ({ page }) => {
  await page.goto('/business');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('Deployments page loads', async ({ page }) => {
  await page.goto('/deployments');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('Gateway Status page loads', async ({ page }) => {
  await page.goto('/gateway');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('AI Tool Catalog page loads', async ({ page }) => {
  await page.goto('/ai-tools');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('Applications page loads', async ({ page }) => {
  await page.goto('/applications');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('External MCP Servers page loads', async ({ page }) => {
  await page.goto('/external-mcp-servers');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('MCP Error Snapshots page loads', async ({ page }) => {
  await page.goto('/mcp/errors');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});

test('Observability page loads', async ({ page }) => {
  await page.goto('/observability');
  await expect(page).not.toHaveTitle(/error/i);
  await expect(page.locator('body')).not.toContainText('Application error');
});
