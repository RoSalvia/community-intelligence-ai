import { expect, test } from "@playwright/test"

test("synthetic demo fills all seven evidence-backed views", async ({ page }) => {
  await page.goto("/")
  await expect(page).toHaveTitle(/Community Intelligence/)
  await page.getByRole("button", { name: "Run synthetic demo" }).click()

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText("120 messages", { exact: true })).toBeVisible()

  for (const pageName of [
    "Campaigns",
    "Communities",
    "Behaviors",
    "Response Patterns",
    "Metric Lab",
    "Evidence",
  ]) {
    await page.getByRole("button", { name: pageName, exact: true }).click()
    await expect(page.getByRole("heading", { name: pageName, exact: true })).toBeVisible()
  }

  const firstEvidence = page.getByRole("button", { name: /^Open evidence_/ }).first()
  await firstEvidence.click()
  await expect(page.getByRole("dialog", { name: "Evidence detail" })).toBeVisible()
  await expect(page.getByText(/not a probability/i)).toBeVisible()
  await page.getByRole("button", { name: "Close evidence" }).click()
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible()
})

test("Telegram JSON import reaches community-only analysis", async ({ page }) => {
  await page.goto("/")
  await page.getByLabel("Select Telegram JSON").setInputFiles(
    "e2e/fixtures/telegram-export.json",
  )

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText("2 messages", { exact: true })).toBeVisible()
  await expect(page.getByText(/Imported · 2 msgs/)).toBeVisible()

  await page.getByRole("button", { name: "Campaigns", exact: true }).click()
  await expect(page.getByText("No campaign data provided")).toBeVisible()
  await expect(page.getByText(/General multilingual semantic judgment: Not implemented/)).toBeVisible()
})
