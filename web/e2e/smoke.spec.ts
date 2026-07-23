import { expect, test } from "@playwright/test";

test("app shell and repo dashboard load", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".brand")).toBeVisible();
  await expect(page.getByRole("button", { name: /Repositories/ })).toBeVisible();
  await expect(page.getByText("Deterministic index")).toBeVisible();
});

test("all navigation screens are reachable for an indexed repo", async ({
  page,
}) => {
  await page.goto("/");
  // Wait for the repo list to load so repo-scoped nav items enable.
  await expect(page.locator(".repo-row").first()).toBeVisible();

  const screens = [
    "Overview",
    "Search",
    "Symbols",
    "Graph",
    "Ask",
    "Explain",
    "Impact",
    "Intelligence",
    "AI layers",
  ];
  for (const name of screens) {
    const item = page.getByRole("button", { name: new RegExp(`^${name}`) });
    await expect(item).toBeEnabled();
    await item.click();
    await expect(page.locator(".panel-title, .stat-grid").first()).toBeVisible();
  }
});
