import { expect, test } from "@playwright/test"

test("Analysis page is accessible", async ({ page }) => {
  await page.goto("/analysis")
  await expect(page.getByRole("heading", { name: "Analysis" })).toBeVisible()
  await expect(
    page.getByText("Live Stockfish stream preview for a FEN position."),
  ).toBeVisible()
})

test("Analysis page has stream controls", async ({ page }) => {
  await page.goto("/analysis")
  await expect(page.getByLabel("FEN")).toBeVisible()
  await expect(page.getByRole("button", { name: "Start stream" })).toBeVisible()
  await expect(page.getByText("Status: idle")).toBeVisible()
})
