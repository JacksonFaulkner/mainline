import { expect, test } from "@playwright/test"

test("System page is accessible", async ({ page }) => {
  await page.goto("/system")
  await expect(page.getByRole("heading", { name: "System" })).toBeVisible()
  await expect(
    page.getByText("Backend health and account connectivity checks."),
  ).toBeVisible()
})
