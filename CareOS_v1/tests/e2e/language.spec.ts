import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

async function openWorkspace(page: Page, request: APIRequestContext) {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const ownerEmail = `language-owner-${suffix}@example.org`
  const email = `language-doctor-${suffix}@example.org`
  const owner = await request.post('/api/v1/auth/register', { data: { email: ownerEmail, password: 'strong-password', full_name: 'Language Owner', organization_name: 'Language Care' } })
  expect(owner.ok()).toBeTruthy()
  const ownerBody = await owner.json()
  const invitation = await request.post('/api/v1/team/invites', { headers: { Authorization: `Bearer ${ownerBody.access_token}` }, data: { email, role: 'doctor' } })
  expect(invitation.ok(), await invitation.text()).toBeTruthy()
  const accepted = await request.post('/api/v1/auth/invitations/accept', { data: { token: (await invitation.json()).development_token, full_name: 'Language Clinician', password: 'strong-password' } })
  expect(accepted.ok(), await accepted.text()).toBeTruthy()
  await page.goto('/#app')
  await page.getByRole('button', { name: 'Sign in to your workspace' }).last().click()
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill('strong-password')
  await page.getByRole('button', { name: /Sign in|تسجيل الدخول/ }).last().click()
  await page.locator('.onboarding-screen, .app-shell').first().waitFor({ state: 'visible' })
  if (await page.locator('.onboarding-screen').isVisible().catch(() => false)) {
    await page.getByRole('textbox', { name: /Organization name|اسم المؤسسة/ }).fill('Language Care')
    await page.getByRole('button', { name: /Continue|متابعة/ }).click()
    await expect(page.locator('.onboarding-screen')).toHaveCount(0)
  }
}

test('Hospital SSO access method is not carried into Create account', async ({ page }) => {
  await page.goto('/#app')
  await page.getByRole('button', { name: 'Hospital SSO' }).click()
  await expect(page.getByText('This is the Hospital SSO route. It uses your organization identity provider to verify your hospital account securely.')).toBeVisible()
  await page.getByRole('tab', { name: 'Create account' }).click()
  await expect(page.getByText('This is the Hospital SSO route. It uses your organization identity provider to verify your hospital account securely.')).toHaveCount(0)
})

test('Arabic and English workspace labels switch together', async ({ page, request }) => {
  await openWorkspace(page, request)
  await page.getByRole('button', { name: 'Switch to Arabic' }).click()
  await expect(page.getByRole('button', { name: 'المساعدة' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'المساعد السريري' })).toBeVisible()
  await page.getByRole('button', { name: 'Switch to English' }).click()
  await expect(page.getByRole('button', { name: 'Help' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Clinical Assistant' })).toBeVisible()
})

test('workspace deep links keep the selected view after navigation', async ({ page, request }) => {
  await openWorkspace(page, request)
  await page.evaluate(() => {
    window.history.pushState({}, '', '#app/patients')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(page.locator('.breadcrumb strong')).toContainText(/Patients|المرضى/)
})
