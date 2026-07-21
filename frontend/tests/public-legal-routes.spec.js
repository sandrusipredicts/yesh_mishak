import { expect, test } from '@playwright/test'

test('privacy policy is public and includes the required disclosures', async ({ page }) => {
  await page.goto('/privacy')

  await expect(page).toHaveURL(/\/privacy$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Privacy Policy' })).toBeVisible()
  await expect(page.getByText('Last updated: July 21, 2026')).toBeVisible()

  for (const section of [
    'Data collected',
    'Google Sign-In usage',
    'Location usage',
    'Notifications',
    'Account deletion',
    'Contact email',
  ]) {
    await expect(page.getByRole('heading', { name: section })).toBeVisible()
  }

  await expect(page.getByRole('link', { name: 'support@yesh-mishak.com' }).first())
    .toHaveAttribute('href', 'mailto:support@yesh-mishak.com')
  await expect(page.locator('[data-testid="auth-checking"]')).toHaveCount(0)
  await expect(page.locator('.language-selection-page')).toHaveCount(0)
})

test('terms are public and include the required terms', async ({ page }) => {
  await page.goto('/terms')

  await expect(page).toHaveURL(/\/terms$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Terms of Service' })).toBeVisible()

  for (const section of [
    'Acceptance of terms',
    'User responsibilities',
    'Game organizer responsibility',
    'Prohibited behavior',
    'Disclaimer',
    'Limitation of liability',
    'Contact information',
  ]) {
    await expect(page.getByRole('heading', { name: section })).toBeVisible()
  }

  await expect(page.getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', '/privacy')
  await expect(page.getByRole('link', { name: 'Yesh Mishak home' })).toHaveAttribute('href', '/')
})

test('the existing public home route links to the legal pages', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })

  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1, name: 'yesh_mishak' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/privacy')
  await expect(page.getByRole('link', { name: 'Terms of Service' })).toHaveAttribute('href', '/terms')
})

test('legal pages do not overflow a small mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 })
  await page.goto('/privacy')

  await expect(page.getByRole('heading', { level: 1, name: 'Privacy Policy' })).toBeVisible()
  const viewportWidths = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))

  expect(viewportWidths.scrollWidth).toBeLessThanOrEqual(viewportWidths.clientWidth)
})
