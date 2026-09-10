import { expect, test } from "@playwright/test"

test("internal M1 harness completes the frozen backend review flow", async ({ page }) => {
  await page.goto("/internal/m1-review")
  await expect(page.getByRole("heading", { name: "Internal M1 Review Harness" })).toBeVisible()

  await page.getByRole("button", { name: "Create workspace" }).click()
  await expect(page.locator("#workspace-result")).toContainText("Wallet Operations Review")

  await page.getByRole("button", { name: "Create all three communities" }).click()
  await expect(page.locator("#communities-result")).toContainText("EN: English Community")
  await expect(page.locator("#communities-result")).toContainText("CN: 中文社区")
  await expect(page.locator("#communities-result")).toContainText("ES: Comunidad Español")

  await page.getByLabel("Upload the supplied synthetic CN Telegram export").setInputFiles(
    "../examples/m1-review-cn-telegram.json",
  )
  await page.getByRole("button", { name: "Upload to CN community" }).click()
  await expect(page.locator("#upload-result")).toContainText("6 messages imported")

  await page.getByRole("button", { name: "Load actors" }).click()
  const moderator = page.getByRole("radio", { name: /陈宁（合成测试 Mod）/ })
  await expect(moderator).toBeVisible()
  await moderator.check()
  await page.getByRole("button", { name: "Mark selected actor as Moderator" }).click()
  await expect(page.locator("#role-result")).toContainText("Moderator saved")

  await page.getByRole("button", { name: "Refresh freshness" }).click()
  await expect(page.locator("#freshness-result")).toContainText("CN:")

  await page.getByRole("button", { name: "Run analysis and auto-poll" }).click()
  await expect(page.locator("#analysis-result")).toContainText("succeeded", { timeout: 30_000 })
  await page.getByRole("button", { name: "Poll latest run now" }).click()
  await expect(page.locator("#analysis-result")).toContainText("new_activity")
  await expect(page.getByRole("alert")).toBeEmpty()
})
