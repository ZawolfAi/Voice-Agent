import { expect, test, type Page, type APIRequestContext } from '@playwright/test'

async function openWorkspace(page: Page, request: APIRequestContext, role = 'admin') {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const ownerEmail = `owner-${suffix}@example.org`
  const email = role === 'admin' ? ownerEmail : `member-${role}-${suffix}@example.org`
  const registration = await request.post('/api/v1/auth/register', { data: { email: ownerEmail, password: 'strong-password', full_name: 'E2E Owner', organization_name: 'E2E Care' } })
  expect(registration.ok()).toBeTruthy()
  let accessToken = (await registration.json()).access_token as string
  if (role !== 'admin') {
    const invitation = await request.post('/api/v1/team/invites', { headers: { Authorization: `Bearer ${accessToken}` }, data: { email, role } })
    expect(invitation.ok(), await invitation.text()).toBeTruthy()
    const invitationToken = (await invitation.json()).development_token as string
    const accepted = await request.post('/api/v1/auth/invitations/accept', { data: { token: invitationToken, full_name: `E2E ${role}`, password: 'strong-password' } })
    expect(accepted.ok()).toBeTruthy()
    accessToken = (await accepted.json()).access_token as string
  }
  await page.goto('/#app')
  await page.getByRole('button', { name: 'Sign in to your workspace' }).last().click()
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill('strong-password')
  await page.getByRole('button', { name: /Sign in|تسجيل الدخول/ }).last().click()
  await page.locator('.onboarding-screen, .app-shell').first().waitFor({ state: 'visible' })
  if (await page.locator('.onboarding-screen').isVisible().catch(() => false)) {
    await page.getByRole('textbox', { name: /Organization name|اسم المؤسسة/ }).fill('CityCare')
    await page.getByRole('button', { name: /Continue|متابعة/ }).click()
    await expect(page.locator('.onboarding-screen')).toHaveCount(0)
  }
}

test('feature routes render after workspace navigation', async ({ page, request }) => {
  await openWorkspace(page, request)
  for (const [route, heading] of [
    ['documents', /DOCUMENTATION|Documentation|التوثيق/],
    ['appointments', /Appointments|المواعيد/],
    ['analytics', /Analytics|التحليلات/],
    ['messages', /Messages|الرسائل/],
  ] as const) {
    await page.evaluate((nextRoute) => {
      window.history.pushState({}, '', `#app/${nextRoute}`)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, route)
    await expect(page.locator('.breadcrumb strong')).toContainText(heading)
  }
})

test('feature controls are interactive', async ({ page, request }) => {
  await openWorkspace(page, request)

  await page.evaluate(() => {
    window.history.pushState({}, '', '#app/patients')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  const patientSearch = page.getByPlaceholder(/Search by name or patient ID|البحث بالاسم أو رقم المريض/)
  await patientSearch.fill('Mariam')
  await expect(patientSearch).toHaveValue('Mariam')

  await page.evaluate(() => {
    window.history.pushState({}, '', '#app/appointments')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await page.getByRole('button', { name: /New appointment|موعد جديد/ }).click()
  await expect(page.locator('.modal')).toBeVisible()
  await page.locator('.modal .icon-btn').click()
  await expect(page.locator('.modal')).toHaveCount(0)

  const calendarRange = page.locator('.calendar-bar strong')
  const initialDate = await calendarRange.textContent()
  await page.getByRole('button', { name: 'Next day' }).click()
  await expect(calendarRange).not.toHaveText(initialDate || '')
  await page.getByRole('button', { name: 'Previous day' }).click()
  await expect(calendarRange).toHaveText(initialDate || '')
  await expect(page.locator('.view-mode-toggle')).toHaveCount(0)

  const calendarToggle = page.getByRole('button', { name: 'Calendar' })
  await calendarToggle.click()
  const monthCalendar = page.locator('.calendar-month-view')
  await expect(monthCalendar).toBeVisible()
  await expect(calendarToggle).toHaveAttribute('aria-expanded', 'true')
  const calendarMonthHeading = page.locator('.calendar-month-heading h2')
  const initialCalendarMonth = await calendarMonthHeading.textContent()
  await page.getByRole('button', { name: 'Next month' }).click()
  await expect(calendarMonthHeading).not.toHaveText(initialCalendarMonth || '')
  await page.getByRole('button', { name: 'Previous month' }).click()
  await expect(calendarMonthHeading).toHaveText(initialCalendarMonth || '')
  const calendarDate = monthCalendar.locator('.calendar-days button').nth(10)
  const selectedDateKey = await calendarDate.getAttribute('data-date')
  const selectedDateLabel = await page.evaluate((dateKey) => {
    const [year, month, day] = (dateKey || '').split('-').map(Number)
    return new Date(year, month - 1, day).toLocaleDateString('en-US', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    })
  }, selectedDateKey)
  await calendarDate.click()
  await expect(monthCalendar).toHaveCount(0)
  await expect(calendarRange).toHaveText(selectedDateLabel)

  await page.evaluate(() => {
    window.history.pushState({}, '', '#app/documents')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(page.locator('input[type="file"]')).toHaveCount(1)

  await page.evaluate(() => {
    window.history.pushState({}, '', '#app/settings')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  const settingsTabs = page.locator('.settings-nav button')
  await settingsTabs.filter({ hasText: 'Preferences' }).click()
  await expect(page.locator('.settings-form .panel-heading h2')).toHaveText('Preferences')
  await page.locator('.settings-theme-options button').filter({ hasText: 'Dark mode' }).click()
  await expect(page.locator('.app-shell')).toHaveClass(/dark-mode/)
  await page.locator('.settings-theme-options button').filter({ hasText: 'Light mode' }).click()
  await settingsTabs.filter({ hasText: 'Security' }).click()
  await expect(page.locator('.settings-form .panel-heading h2')).toHaveText('Security')
  await expect(page.getByText('Two-step verification', { exact: true })).toBeVisible()
  await settingsTabs.filter({ hasText: 'Notifications' }).click()
  await expect(page.locator('.settings-form .panel-heading h2')).toHaveText('Notifications')
})

test('general chat is available to non-clinical staff without patient context', async ({ page, request }) => {
  await openWorkspace(page, request, 'receptionist')

  const chatToggle = page.getByRole('button', { name: 'Open general chat' })
  await expect(chatToggle).toBeVisible()
  await chatToggle.click()
  await expect(page.getByRole('dialog', { name: 'General chat' })).toBeVisible()
  await expect(page.locator('.global-chat-panel select')).toHaveCount(0)
  await page.getByRole('textbox', { name: 'Message the assistant' }).fill('Hello')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.global-chat-message.assistant').last()).toContainText('Demo assistant received: Hello.')
})

test('patient code is visible and can find the patient record', async ({ page, request }) => {
  const login = await request.post('/api/v1/auth/demo-login', {
    data: { role: 'admin', username: 'admin.demo', password: 'Admin@123' },
  })
  expect(login.ok()).toBeTruthy()
  const token = (await login.json()).access_token as string
  await page.goto('/#app')
  await page.evaluate((accessToken) => localStorage.setItem('careos-access-token', accessToken), token)
  await page.reload()
  await page.goto('/#app/patients')

  const patientCode = page.locator('.patient-code').first()
  await expect(patientCode).toBeVisible()
  const code = (await patientCode.textContent())?.trim() ?? ''
  expect(code).toMatch(/^PAT-\d{12}$/)
  await page.getByPlaceholder(/Search by name or patient ID|البحث بالاسم أو رقم المريض/).fill(code)
  await expect(page.locator('.patient-table-row')).toHaveCount(1)
})

test('workspace remains usable at mobile width without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#app')
  await expect(page.locator('body')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)
})

test('local demo personas expose staff and patient sessions', async ({ request }) => {
  const accounts = [
    ['admin', 'admin.demo', 'Admin@123'],
    ['doctor', 'doctor.demo', 'Doctor@123'],
    ['nurse', 'nurse.demo', 'Nurse@123'],
    ['receptionist', 'reception.demo', 'Reception@123'],
    ['hospital_director', 'director.demo', 'Director@123'],
    ['it_admin', 'itadmin.demo', 'ITAdmin@123'],
    ['administrative_staff', 'staff.demo', 'Staff@123'],
  ] as const
  for (const [role, username, password] of accounts) {
    const response = await request.post('/api/v1/auth/demo-login', { data: { role, username, password } })
    expect(response.ok(), `${role}: ${await response.text()}`).toBeTruthy()
    expect((await response.json()).access_token).toBeTruthy()
  }
  const patient = await request.post('/api/v1/auth/demo-login', { data: { role: 'patient', username: 'patient.demo', password: 'Patient@123' } })
  expect(patient.ok(), await patient.text()).toBeTruthy()
  expect((await patient.json()).portal_access_token).toBeTruthy()
})

test('demo patient opens the patient portal with its own record', async ({ page, request }) => {
  const response = await request.post('/api/v1/auth/demo-login', { data: { role: 'patient', username: 'patient.demo', password: 'Patient@123' } })
  expect(response.ok()).toBeTruthy()
  const token = (await response.json()).portal_access_token as string
  await page.goto('/#app')
  await page.evaluate((portalToken) => localStorage.setItem('careos-portal-token', portalToken), token)
  await page.reload()
  await expect(page.getByText('Mariam Hassan')).toBeVisible()
  await expect(page.locator('.portal-patient-id code')).toHaveText(/^PAT-\d{12}$/)
  const portalTabs = page.locator('.portal-tabs button')
  await expect(portalTabs).toHaveCount(4)
  await portalTabs.nth(1).click()
  await expect(page.locator('.portal-section')).toBeVisible()
  await portalTabs.nth(2).click()
  await expect(page.locator('.portal-section form')).toBeVisible()
  await portalTabs.nth(3).click()
  await expect(page.locator('.portal-section')).toBeVisible()
  const sidebar = page.getByRole('complementary')
  await sidebar.getByRole('button', { name: 'Appointments' }).click()
  await expect(page).toHaveURL(/#app\/appointments$/)
  await expect(page.locator('.portal-section .panel-heading h2')).toHaveText('Appointments')
  await sidebar.getByRole('button', { name: 'Messages' }).click()
  await expect(page).toHaveURL(/#app\/messages$/)
  await expect(page.locator('.portal-section form')).toBeVisible()
})

test('staff users are redirected from the patient-only portal', async ({ page, request }) => {
  await openWorkspace(page, request, 'receptionist')
  await page.evaluate(() => {
    window.history.pushState({}, '', '#app/portal')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(page).toHaveURL(/#app\/dashboard$/)
  await expect(page.getByText('Authentication required')).toHaveCount(0)
})

test('demo clinician can open the patient-aware assistant', async ({ page }) => {
  await page.goto('/#app')
  await page.getByRole('button', { name: 'Sign in to your workspace' }).last().click()
  await page.getByRole('button', { name: 'Login as Doctor', exact: true }).click()
  await expect(page.locator('.app-shell')).toBeVisible()
  await page.evaluate(() => {
    window.history.pushState({}, '', '#app/assistant')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(page.locator('select')).toHaveValue(/.+/)
  await page.locator('textarea').fill('Summarize the current patient context')
  await page.getByRole('button', { name: /Ask assistant|اسأل المساعد/ }).click()
  await expect(page.locator('.assistant-answer')).toContainText(/Sandbox response|unavailable|not configured|غير متاح|غير مهيأ/i)
})

test('operations dashboard excludes clinical and admin-only controls', async ({ page, request }) => {
  await openWorkspace(page, request, 'receptionist')
  await expect(page.getByRole('heading', { name: 'Operations overview' })).toBeVisible()
  await expect(page.getByRole('navigation').getByRole('button', { name: 'Clinical Assistant' })).toHaveCount(0)
  await expect(page.getByRole('navigation').getByRole('button', { name: 'Settings' })).toHaveCount(0)
  await expect(page.getByRole('navigation').getByRole('button', { name: 'Integrations' })).toHaveCount(0)
  await expect(page.getByText('AI drafts reviewed')).toHaveCount(0)
})

test('profile card opens the account page', async ({ page, request }) => {
  await openWorkspace(page, request, 'doctor')
  await page.locator('.profile-card').click()
  await expect(page.locator('.account-profile-panel h2')).toHaveText('E2E doctor')
  await expect(page.getByRole('heading', { name: 'Account security' })).toBeVisible()
})

test('role protection redirects a doctor from restricted audit routes', async ({ page, request }) => {
  await openWorkspace(page, request, 'doctor')
  await page.evaluate(() => {
    window.history.pushState({}, '', '#app/teamAudit')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(page).not.toHaveURL(/#app\/teamAudit$/)
  await expect(page.locator('.breadcrumb strong')).not.toContainText(/Team|Audit|الفريق|التدقيق/)
})

for (const scenario of [
  { role: 'doctor', allowed: 'notes', restricted: 'teamAudit' },
  { role: 'nurse', allowed: 'notes', restricted: 'teamAudit' },
  { role: 'receptionist', allowed: 'appointments', restricted: 'notes' },
  { role: 'hospital_director', allowed: 'reports', restricted: 'notes' },
  { role: 'it_admin', allowed: 'integrations', restricted: 'patients' },
  { role: 'administrative_staff', allowed: 'appointments', restricted: 'notes' },
] as const) {
  test(`route guard enforces ${scenario.role} navigation`, async ({ page, request }) => {
    await openWorkspace(page, request, scenario.role)
    await page.evaluate((route) => { window.history.pushState({}, '', `#app/${route}`); window.dispatchEvent(new PopStateEvent('popstate')) }, scenario.allowed)
    await expect(page).toHaveURL(new RegExp(`#app/${scenario.allowed}$`))
    await page.evaluate((route) => { window.history.pushState({}, '', `#app/${route}`); window.dispatchEvent(new PopStateEvent('popstate')) }, scenario.restricted)
    await expect(page).not.toHaveURL(new RegExp(`#app/${scenario.restricted}$`))
  })
}
