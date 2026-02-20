import { expect, test } from "@playwright/test"

test("Play page is accessible", async ({ page }) => {
  await page.goto("/play")
  await expect(page.getByRole("heading", { name: "Play" })).toBeVisible()
  await expect(
    page.getByText("Create seeks against incoming opponents on Lichess."),
  ).toBeVisible()
})

test("Play page shows seek controls", async ({ page }) => {
  await page.goto("/play")
  await expect(page.getByLabel("Minutes")).toBeVisible()
  await expect(page.getByLabel("Increment")).toBeVisible()
  await expect(page.getByRole("button", { name: "Create seek" })).toBeVisible()
})
