import { expect, test } from "@playwright/test"

test("History page is accessible", async ({ page }) => {
  await page.goto("/history")
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible()
  await expect(
    page.getByText("Recent completed games and outcomes."),
  ).toBeVisible()
})

test("History page renders loading, table, or error state", async ({ page }) => {
  await page.goto("/history")
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible()
  const loadingVisible = await page.getByText("Loading games...").isVisible()
  const tableVisible = await page.getByRole("table").isVisible()
  const errorVisible = await page.getByText(/error|detail/i).first().isVisible()

  expect(loadingVisible || tableVisible || errorVisible).toBeTruthy()
})
