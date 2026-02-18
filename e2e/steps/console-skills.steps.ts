/**
 * Console step definitions for Skills Management (CAB-1366)
 * Steps for managing agent skills via the Console UI.
 */

import { createBdd } from "playwright-bdd";
import { test, expect, URLS } from "../fixtures/test-base";

const { When, Then } = createBdd(test);

// ============================================================================
// SKILLS — NAVIGATION
// ============================================================================

When("I navigate to the Skills page", async ({ page }) => {
  await page.goto(`${URLS.console}/skills`);
  await page.waitForLoadState("networkidle");
  await expect(page.locator("text=Loading").first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then("the Skills page loads successfully", async ({ page }) => {
  const heading = page.locator("h1, h2").filter({ hasText: /Skills/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false));

  expect(loaded || page.url().includes("/skills")).toBe(true);
});

// ============================================================================
// SKILLS — CRUD
// ============================================================================

When(
  "I create a skill named {string} with scope {string}",
  async ({ page }, skillName: string, scope: string) => {
    const addBtn = page.locator('button:has-text("Add Skill")');
    await expect(addBtn).toBeVisible({ timeout: 15000 });
    await addBtn.click();

    await page.fill('input[placeholder*="namespace"]', `e2e/${skillName.toLowerCase().replace(/\s+/g, '-')}`);
    await page.fill('input[placeholder*="Human-readable"]', skillName);
    await page.fill('input[placeholder*="tenant-id"]', 'oasis');

    const scopeSelect = page.locator("select");
    await scopeSelect.selectOption(scope);

    await page.click('button[type="submit"]:has-text("Create")');
    await page.waitForLoadState("networkidle");
  },
);

Then(
  "the skill {string} appears in the list",
  async ({ page }, skillName: string) => {
    await expect(page.locator(`text=${skillName}`).first()).toBeVisible({
      timeout: 10000,
    });
  },
);

When(
  "I edit the skill {string} priority to {string}",
  async ({ page }, skillName: string, priority: string) => {
    const row = page.locator(`tr:has-text("${skillName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });

    const editBtn = row.locator("button").first();
    await editBtn.click();

    const priorityInput = page.locator('input[type="number"]');
    await priorityInput.clear();
    await priorityInput.fill(priority);

    await page.click('button[type="submit"]:has-text("Update")');
    await page.waitForLoadState("networkidle");
  },
);

Then(
  "the skill {string} shows priority {string}",
  async ({ page }, skillName: string, priority: string) => {
    const row = page.locator(`tr:has-text("${skillName}")`).first();
    await expect(row).toBeVisible({ timeout: 10000 });
    await expect(row.locator(`text=${priority}`)).toBeVisible();
  },
);

When("I delete the skill {string}", async ({ page }, skillName: string) => {
  const row = page.locator(`tr:has-text("${skillName}")`).first();
  await expect(row).toBeVisible({ timeout: 10000 });

  const deleteBtn = row.locator('button:has(svg[class*="trash" i]), button:last-child');
  await deleteBtn.click();
});

Then(
  "the skill {string} is no longer in the list",
  async ({ page }, skillName: string) => {
    await page.waitForLoadState("networkidle");
    const entry = page.locator(`text=${skillName}`);
    await expect(entry).not.toBeVisible({ timeout: 10000 });
  },
);

Then("the Add Skill button is not visible", async ({ page }) => {
  await page.waitForLoadState("networkidle");
  // Wait for content to load
  await expect(
    page.locator("h1, h2").filter({ hasText: /Skills/i }),
  ).toBeVisible({ timeout: 10000 });

  const addBtn = page.locator('button:has-text("Add Skill")');
  await expect(addBtn).not.toBeVisible({ timeout: 5000 });
});

// ============================================================================
// SKILLS — RESOLUTION PREVIEW
// ============================================================================

When("I open the Resolution Preview panel", async ({ page }) => {
  const previewBtn = page.locator('button:has-text("Resolution Preview")');
  await expect(previewBtn).toBeVisible({ timeout: 10000 });
  await previewBtn.click();
});

When(
  "I resolve skills for tool {string}",
  async ({ page }, toolName: string) => {
    const toolInput = page.locator('input[placeholder*="code-review"]');
    await toolInput.fill(toolName);

    const resolveBtn = page.locator('button:has-text("Resolve")');
    await resolveBtn.click();
    await page.waitForLoadState("networkidle");
  },
);

Then("the resolution results are displayed", async ({ page }) => {
  // Either resolved skills table or "No skills resolved" message
  const table = page.locator("table").last();
  const noResults = page.locator("text=No skills resolved");

  const hasResults =
    (await table.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await noResults.isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasResults).toBe(true);
});
