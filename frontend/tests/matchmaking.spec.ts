import { expect, test } from "@playwright/test"

test("Matchmaking page is accessible", async ({ page }) => {
  await page.goto("/matchmaking")
  await expect(page.getByRole("heading", { name: "Matchmaking" })).toBeVisible()
  await expect(
    page.getByText("Challenge stream and accept/decline flows will be migrated here next."),
  ).toBeVisible()
})
