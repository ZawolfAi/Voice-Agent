import { expect, test } from '@playwright/test'

test('offline demo login still opens the app without backend database', async ({ page }) => {
  await page.goto('http://127.0.0.1:5173/#app')

  await page.getByRole('button', { name: 'Login as Doctor', exact: true }).click()

  await expect(page.locator('.app-shell')).toBeVisible({ timeout: 15000 })
  await expect(page).toHaveURL(/#app\/(dashboard|portal|account)$/)
})
