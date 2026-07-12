import { expect, test } from '@playwright/test'


async function seedEnglishReturningUser(page) {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
}


test('valid verification link shows success and returns to login', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'verified', message: 'Email verified successfully.' }),
  }))

  await page.goto(`/verify-email?token=${'a'.repeat(48)}`)

  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  await expect(page.getByText('Your email is verified. You can sign in now.')).toBeVisible()
  await page.getByRole('button', { name: 'Back to sign in' }).click()
  await expect(page.getByRole('tab', { name: 'Login' })).toBeVisible()
  await expect(page).toHaveURL(/\/$/)
})


test('expired verification link shows a safe actionable message', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'expired', message: 'This verification link has expired.' }),
  }))

  await page.goto(`/verify-email?token=${'b'.repeat(48)}`)

  await expect(page.getByText('This verification link has expired. Request a new one.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back to sign in' })).toBeVisible()
})


test('backend EMAIL_NOT_VERIFIED response moves password login to verification screen', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/login', (route) => route.fulfill({
    status: 403,
    contentType: 'application/json',
    body: JSON.stringify({
      error: true,
      code: 'EMAIL_NOT_VERIFIED',
      message: 'Email verification is required before signing in.',
    }),
  }))

  await page.goto('/')
  await page.getByLabel('Username or Email').fill('pending@example.com')
  await page.getByLabel('Password').fill('strongpass123')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  await expect(page.getByText('We sent a verification link to pending@example.com.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send again' })).toBeVisible()
})
